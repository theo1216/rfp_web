import json
import re
from collections import Counter
from io import BytesIO

import streamlit as st
from pypdf import PdfReader

st.set_page_config(page_title="RFP AI 분석 도우미", page_icon="🔍", layout="wide")

st.markdown(
    """
    <style>
    .block-container {max-width: 1180px; padding-top: 1.8rem; padding-bottom: 3rem;}
    .hero {padding: 26px 30px; border-radius: 18px; background: linear-gradient(135deg,#eef4ff,#f8fbff); border: 1px solid #dbeafe; margin-bottom: 1rem;}
    .hero-badge {display:inline-block; padding:6px 14px; border-radius:999px; background:linear-gradient(135deg,#1a4f8a,#2563c4); color:#fff; font-size:12px; font-weight:700;}
    .chip {display:inline-block; margin:4px 6px 4px 0; padding:6px 12px; border-radius:999px; color:#fff; font-size:12px; font-weight:700;}
    .soft {background:#f8fbff; border-left:4px solid #2563c4; padding:14px 16px; border-radius:10px;}
    .warn {background:#fffbeb; border-left:4px solid #f59e0b; padding:14px 16px; border-radius:10px;}
    </style>
    """,
    unsafe_allow_html=True,
)

TAG_COLORS = ["#1a4f8a","#2563c4","#0369a1","#0e7490","#047857","#6d28d9","#7c3aed","#b45309","#be185d","#c2410c"]
STOPWORDS = {
    "그리고","그러나","또한","위한","통한","대한","관련","기반","분석","연구","과제","사업","수행","추진",
    "제안","계획","방안","자료","문서","추가","직접","입력","활용","검토","지원","개선","도출","구축","개발",
    "정부","국가","한국","대한민국","분야","중심","내용","목표","필요","현재","향후","이번","이상","아래",
    "the","and","for","with","from","that","this","into","using","based"
}
DOMAIN_HINTS = {
    "ai_data": ["ai","인공지능","데이터","플랫폼","알고리즘","모델","디지털","llm"],
    "policy": ["정책","평가","성과","거버넌스","전략","제도","로드맵","기획"],
    "bio_health": ["바이오","의료","헬스","진단","유전체","약물","질환"],
    "climate_energy": ["탄소","에너지","기후","환경","전력","배터리","수소"],
    "manufacturing": ["제조","공정","소재","부품","장비","로봇","자동화"],
}
FOCUS = {
    "ai_data": "디지털 전환과 데이터 기반 의사결정 체계의 실효성",
    "policy": "정책 실행력과 성과관리 체계의 정합성",
    "bio_health": "실증 가능성과 공공적 파급효과",
    "climate_energy": "탄소중립 대응과 실증 확산 가능성",
    "manufacturing": "현장 적용성과 공정 혁신 가능성",
    "general": "정책적 필요성과 실행 가능성",
}

def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\x00", " ")).strip()

def clip(text: str, limit: int = 800) -> str:
    text = normalize(text)
    return text if len(text) <= limit else text[:limit].rstrip() + "..."

def read_pdf(uploaded_file):
    if uploaded_file is None:
        return "", {}
    try:
        reader = PdfReader(BytesIO(uploaded_file.getvalue()))
        text = []
        for page in reader.pages[:40]:
            try:
                text.append(page.extract_text() or "")
            except Exception:
                pass
        md = reader.metadata or {}
        meta = {
            "title": getattr(md, "title", None),
            "author": getattr(md, "author", None),
            "subject": getattr(md, "subject", None),
        }
        return normalize("\n".join(text)), meta
    except Exception as e:
        return "", {"error": str(e)}

def tokenize(text: str):
    words = re.findall(r"[A-Za-z가-힣0-9\-\+]{2,}", text or "")
    result = []
    for w in words:
        w = w.lower().strip()
        if w in STOPWORDS or w.isdigit():
            continue
        result.append(w)
    return result

def extract_keywords(text: str, fallback: str = "", limit: int = 10):
    counter = Counter(tokenize(text))
    items = [w for w, _ in counter.most_common(40)]
    for w in tokenize(fallback):
        if w not in items:
            items.append(w)
    final = []
    for w in items:
        if len(w) < 2:
            continue
        if w not in final:
            final.append(w)
    for w in ["정책수요","추진전략","성과관리","실행체계","확산가능성"]:
        if len(final) >= limit:
            break
        if w not in final:
            final.append(w)
    return final[:limit]

def detect_domain(text: str):
    text = (text or "").lower()
    best, score = "general", 0
    for domain, hints in DOMAIN_HINTS.items():
        s = sum(1 for h in hints if h in text)
        if s > score:
            best, score = domain, s
    return best

def build_payload(mode, rfp_file, rfp_text, extra1, extra2, extra_note):
    if mode == "upload" and rfp_file is not None:
        main_text, _ = read_pdf(rfp_file)
        main_name = rfp_file.name
        source_type = "pdf"
    else:
        main_text = normalize(rfp_text)
        main_name = "직접 입력"
        source_type = "text"

    extra_files = []
    for file_obj in [extra1, extra2]:
        if file_obj is None:
            continue
        txt, meta = read_pdf(file_obj)
        extra_files.append({"name": file_obj.name, "text": txt, "meta": meta})

    combined = normalize("\n".join([main_text] + [x["text"] for x in extra_files] + [extra_note or ""]))
    fallback = " ".join([main_name] + [x["name"] for x in extra_files] + [extra_note or ""])
    keywords = extract_keywords(combined, fallback, 10)
    return {
        "source_type": source_type,
        "rfp_name": main_name,
        "rfp_text": main_text,
        "extra_files": extra_files,
        "extra_note": normalize(extra_note),
        "combined": combined,
        "preview": clip(combined),
        "keywords": keywords,
        "domain": detect_domain(combined + " " + fallback),
        "text_extracted": bool(main_text),
    }

def make_analysis(payload):
    k = payload["keywords"] + ["정책수요","실행체계","성과관리","확산전략"]
    k1, k2, k3, k4 = k[:4]
    focus = FOCUS.get(payload["domain"], FOCUS["general"])
    extra_bits = []
    if payload["extra_files"]:
        extra_bits.append(f"추가 PDF {len(payload['extra_files'])}건")
    if payload["extra_note"]:
        extra_bits.append("직접 입력 참고 정보")
    extra_phrase = ", ".join(extra_bits) if extra_bits else "RFP 본문"

    intent = (
        f"이 과제의 발주 의도는 {k1}·{k2}와 관련된 수요를 단순한 현황 정리 수준이 아니라 실행 가능한 전략으로 구조화하는 데 있습니다. "
        f"발주기관은 배경 설명만 반복하는 보고서보다 실제 의사결정에 바로 사용할 수 있는 분석 틀과 우선순위, 실행 대안을 확보하려는 성격이 강합니다.\n\n"
        f"왜 지금 이 과제가 필요한지의 관점에서 보면 핵심은 {focus}에 대한 대응을 더 미루기 어렵다는 점입니다. "
        f"환경 변화 속도가 빨라질수록 정책·사업 설계 기준을 다시 세워야 하고, 그에 따라 추진 전략과 성과관리 체계가 함께 요구됩니다.\n\n"
        f"이번 입력에서는 {extra_phrase}가 함께 제공되었기 때문에, 일반론적 제안보다 기관 상황과 축적된 맥락을 반영한 맞춤형 접근이 필요하다고 해석하는 것이 타당합니다. "
        f"따라서 제안서는 RFP 문구를 반복하기보다 추가 자료에 나타난 조건과 제약을 본문 논리 안으로 흡수하는 방식으로 구성하는 편이 적절합니다.\n\n"
        f"결론적으로 발주자는 {k3}와 {k4}를 연결하는 실무형 제안서를 기대한다고 볼 수 있습니다. "
        f"즉, 분석의 깊이와 함께 실행 체계, 일정, 성과 활용 시나리오까지 한 번에 제시하는 문서가 높은 평가를 받을 가능성이 큽니다."
    )

    criteria = [
        {"항목":"과업이해도 및 목표타당성","비중":"25%","핵심포인트":f"{k1}과 {k2}가 왜 핵심 문제인지 선명하게 재구성해야 합니다. 목표는 선언형 문구보다 문제정의-해결경로-산출물의 연결 구조로 제시하는 편이 유리합니다."},
        {"항목":"연구방법 및 추진전략","비중":"25%","핵심포인트":f"{focus}를 구현할 수 있는 단계별 방법론을 제시해야 합니다. 조사·분석·실증·환류의 흐름을 끊김 없이 설계하고, 각 단계의 검증 기준을 분명히 적는 것이 중요합니다."},
        {"항목":"추진체계 및 수행역량","비중":"20%","핵심포인트":"총괄-실무-자문 역할을 구분해 책임소재를 명확히 보여줘야 합니다. 추가 자료의 기존 실적이나 유사 경험이 있다면 정량 근거로 전환하는 구성이 효과적입니다."},
        {"항목":"성과확산 및 활용가능성","비중":"20%","핵심포인트":f"{k3}가 실제 제도개선, 정책반영, 후속사업화로 이어지는 활용 시나리오를 제시해야 합니다. 결과물이 발주기관의 의사결정에 어떻게 직접 쓰일지까지 보여줘야 합니다."},
        {"항목":"예산편성의 적정성","비중":"10%","핵심포인트":"인건비, 조사·분석비, 자문비를 산출물과 직접 연결해 설명해야 합니다. 비용 항목마다 왜 필요한지와 단계별 투입 논리를 함께 제시하면 설득력이 높아집니다."},
    ]

    strategy = {
        "전체방향": (
            f"제안서 전체는 '{k1}를 둘러싼 문제를 {k2} 중심의 실행전략으로 해결한다'는 메시지로 묶는 편이 좋습니다. "
            f"단순 현황정리보다 문제정의, 제약요인, 실행 시나리오, 활용 결과를 순차적으로 제시해야 설득력이 높아집니다.\n\n"
            f"특히 추가 자료에 포함된 기관 실적과 특이사항은 별도 참고사항으로 두지 말고, 왜 우리 기관이 적합한가를 설명하는 증거 블록으로 재배치하는 구성이 유리합니다."
        ),
        "섹션별전략": [
            {"섹션":"과업 이해 및 발주 배경","전략":f"{k1}과 {k2}를 중심으로 현재 상황의 문제를 구조화하고, 발주기관이 당장 해결하고자 하는 쟁점을 압축해 보여줘야 합니다."},
            {"섹션":"추진 방법론 및 세부 수행내용","전략":"착수-진단-분석-전략수립-환류의 5단 흐름으로 설계하면 안정적입니다. 각 단계에서 사용할 데이터, 분석 프레임, 산출물을 구체적으로 적어야 합니다."},
            {"섹션":"추진체계 및 역할분담","전략":"총괄책임자, 세부 실무책임자, 외부 자문단 기능을 구분해 역할 중복을 줄여야 합니다. 의사결정 체계와 품질관리 절차를 도식화하면 신뢰도가 높아집니다."},
            {"섹션":"성과관리 및 활용계획","전략":f"{k3}와 {k4}를 중심으로 성과를 산출물 자체보다 정책 반영 가능성, 후속 사업 연계성, 기관 내 내재화 수준으로 정의하는 편이 적절합니다."},
            {"섹션":"기관 경쟁력 및 차별화","전략":"보유 데이터, 유사 과제 경험, 정책 네트워크, 전문가 풀을 근거 중심으로 제시해야 합니다. 추가 자료의 기존 실적은 숫자와 사례 중심으로 재정리하는 편이 효과적입니다."},
        ],
        "차별화포인트": "1) 추가 자료를 별첨이 아니라 본문 근거로 직접 연결\n2) 연구방법을 단계별 검증 질문과 산출물 기준으로 제시\n3) 최종 결과물이 발주기관 내부 의사결정에 어떻게 쓰일지 활용 시나리오까지 명시",
    }

    qas = [
        {"질문":"왜 이 과제가 지금 시점에 꼭 필요한가?","답변":f"본 과제는 {k1}를 둘러싼 수요가 누적된 상황에서 이를 실행전략으로 전환해야 하는 시점이라는 점에 의미가 있습니다. 제안서는 현황 설명보다 즉시 활용 가능한 정책 설계와 실행 근거 제시에 초점을 맞추고 있습니다."},
        {"질문":"제안한 방법론이 실제로 작동할 것이라는 근거는 무엇인가?","답변":f"방법론을 자료수집-진단-분석-전략수립-환류의 단계로 구분하고 각 단계별 산출물을 명확히 설정했습니다. 따라서 {k2}를 추상적으로 설명하는 것이 아니라 중간 검증이 가능한 구조로 설계했다는 점이 강점입니다."},
        {"질문":"귀 기관이 이 과제를 수행하기에 적합한 이유는 무엇인가?","답변":"RFP 외에 제공된 추가 자료의 기존 실적과 기관 특성을 제안 논리 안에 직접 반영할 수 있다는 점이 경쟁력입니다. 이를 통해 발주기관 관점의 이해도와 실제 수행 역량을 동시에 입증하는 구성이 가능합니다."},
        {"질문":"최종 성과는 어떤 방식으로 활용될 수 있는가?","답변":f"최종 성과는 보고서 제출에 그치지 않고 발주기관의 내부 의사결정, 사업 설계, 후속과제 기획에 바로 활용될 수 있도록 설계했습니다. 특히 {k3}와 연계한 실행안, 우선순위, 관리지표까지 함께 제시하는 방향이 적절합니다."},
        {"질문":"경쟁 제안서와 비교해 차별적인 부분은 무엇인가?","답변":"추가 자료를 단순 참고가 아니라 차별화 근거로 재구성한다는 점이 가장 큰 차이입니다. 또한 수행체계와 성과활용 계획을 한 세트로 설계해 실제 적용 가능성을 더 선명하게 보여줄 수 있습니다."},
    ]

    return {"발주의도": intent, "평가기준": criteria, "핵심키워드": payload["keywords"], "작성전략": strategy, "예상QA": qas}

def make_refs():
    return {"유사과제": [], "관련논문": []}

def build_copy_text(result, refs):
    t = "═══════════════════════════════════\n  RFP AI 분석 결과 (데모 모드)\n═══════════════════════════════════\n\n"
    t += "【 발주 의도 】\n" + result.get("발주의도","") + "\n\n"
    t += "【 평가 기준 】\n"
    for i, item in enumerate(result.get("평가기준", []), 1):
        t += f"{i}. {item['항목']} ({item['비중']})\n   → {item['핵심포인트']}\n"
    t += "\n【 핵심 키워드 】\n" + "  ".join([f"#{i} {kw}" for i, kw in enumerate(result.get("핵심키워드", []), 1)]) + "\n\n"
    t += "【 작성 전략 】\n▶ 전체 방향\n" + result.get("작성전략", {}).get("전체방향","") + "\n\n▶ 섹션별 전략\n"
    for i, item in enumerate(result.get("작성전략", {}).get("섹션별전략", []), 1):
        t += f"{i}. {item['섹션']}\n   {item['전략']}\n"
    t += "\n▶ 차별화 포인트\n" + result.get("작성전략", {}).get("차별화포인트","") + "\n\n"
    t += "【 예상 질문 & 답변 】\n"
    for i, item in enumerate(result.get("예상QA", []), 1):
        t += f"Q{i}. {item['질문']}\nA. {item['답변']}\n\n"
    t += "【 유사 과제 】\n- 현재 데모 모드에서는 실제 검색을 수행하지 않습니다.\n\n"
    t += "【 관련 논문 】\n- 현재 데모 모드에서는 실제 검색을 수행하지 않습니다.\n"
    return t

def render_keywords(words):
    html = "".join(
        [f"<span class='chip' style='background:{TAG_COLORS[i % len(TAG_COLORS)]}'>#{i+1} {w}</span>" for i, w in enumerate(words)]
    )
    st.markdown(html, unsafe_allow_html=True)

for key in ["analysis_result", "refs_result", "copy_text", "payload_preview"]:
    if key not in st.session_state:
        st.session_state[key] = None

st.markdown(
    """
    <div class="hero">
      <span class="hero-badge">🔍 RFP_AI_1.0</span>
      <h1 style="margin:14px 0 8px 0;color:#0f172a;">RFP AI 분석 도우미</h1>
      <p style="margin:0;color:#475569;line-height:1.7;">
        지금 버전은 Streamlit 웹 UI 데모입니다. RFP 업로드, 추가 자료 입력, 결과 화면, 다운로드 동선까지 먼저 구현하고,
        Claude API와 웹 검색은 나중에 함수만 연결할 수 있게 분리해 둔 구조입니다.
      </p>
    </div>
    """,
    unsafe_allow_html=True,
)

st.info("현재는 데모 모드입니다. PDF 텍스트는 로컬에서 추출해 화면을 구성하고, 유사 과제·논문 검색은 비활성 상태로 둡니다.")

with st.sidebar:
    st.subheader("현재 상태")
    st.success("웹 UI 완료")
    st.warning("Claude API 미연결")
    st.markdown("나중에 추가할 항목\n- Claude API 호출\n- 웹 검색 결과 파싱\n- `st.secrets` 연동")

left, right = st.columns([1.15, 0.85], gap="large")

with left:
    st.header("입력")
    tab_upload, tab_text = st.tabs(["📎 PDF 업로드", "✏️ 직접 입력"])

    with tab_upload:
        rfp_file = st.file_uploader("RFP PDF", type=["pdf"], key="rfp_file")
    with tab_text:
        rfp_text = st.text_area("RFP 내용 직접 입력", height=240, key="rfp_text")

    with st.expander("선택 입력 · 추가 자료", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            extra_file_1 = st.file_uploader("추가 PDF 1", type=["pdf"], key="extra_file_1")
        with col2:
            extra_file_2 = st.file_uploader("추가 PDF 2", type=["pdf"], key="extra_file_2")
        extra_note = st.text_area(
            "직접 입력 참고 정보",
            height=140,
            key="extra_note",
            placeholder="기관 기존 실적, 특이사항, 경쟁기관 정보, 발주처 특성 등을 입력하세요.",
        )

    input_mode = "upload" if rfp_file is not None else "text"

    if st.button("🔍 RFP 분석 시작", use_container_width=True, type="primary"):
        if rfp_file is None and not (rfp_text or "").strip():
            st.error("RFP PDF를 업로드하거나 RFP 내용을 직접 입력해야 합니다.")
        else:
            progress = st.progress(0)
            status = st.empty()

            status.info("입력 자료를 정리하는 중입니다...")
            progress.progress(25)
            payload = build_payload(input_mode, rfp_file if input_mode == "upload" else None, rfp_text, extra_file_1, extra_file_2, extra_note)

            status.info("데모 분석 결과를 생성하는 중입니다...")
            progress.progress(65)
            result = make_analysis(payload)
            refs = make_refs()

            status.info("결과 화면을 구성하는 중입니다...")
            progress.progress(90)
            st.session_state.analysis_result = result
            st.session_state.refs_result = refs
            st.session_state.copy_text = build_copy_text(result, refs)
            st.session_state.payload_preview = payload

            progress.progress(100)
            status.success("완료되었습니다. 아래 결과를 확인하세요.")

with right:
    st.header("입력 요약")
    preview = st.session_state.payload_preview
    if preview is None:
        st.caption("아직 분석을 실행하지 않았습니다.")
        st.markdown("- RFP는 PDF 업로드 또는 직접 입력 중 하나만 있으면 됩니다.\n- 추가 PDF 2건과 직접 입력 메모를 함께 넣을 수 있습니다.\n- 현재는 웹 UI 데모이므로 참고자료 검색은 비활성입니다.")
    else:
        st.markdown(f"<div class='soft'><b>RFP 입력 방식</b>: {preview['source_type']}<br><b>RFP 이름</b>: {preview['rfp_name']}<br><b>추가 파일 수</b>: {len(preview['extra_files'])}건<br><b>직접 입력 참고 정보</b>: {'있음' if preview['extra_note'] else '없음'}</div>", unsafe_allow_html=True)
        st.markdown("#### 추출 미리보기")
        if preview["preview"]:
            st.write(preview["preview"])
        else:
            st.warning("PDF에서 텍스트를 추출하지 못했습니다. 스캔 PDF라면 현재 데모 모드에서는 내용 인식이 제한될 수 있습니다.")
        if preview["extra_files"]:
            st.markdown("#### 추가 파일")
            for item in preview["extra_files"]:
                st.markdown(f"- {item['name']}")

result = st.session_state.analysis_result
refs = st.session_state.refs_result

if result:
    st.markdown("---")
    st.header("결과")
    st.warning("아래 결과는 Claude API 없이 동작하는 데모 초안입니다. 실제 분석·검색 로직은 나중에 함수만 교체하면 됩니다.")

    st.subheader("🎯 발주 의도")
    st.write(result["발주의도"])

    st.subheader("📊 평가기준")
    for item in result["평가기준"]:
        st.markdown(f"**{item['항목']}** · {item['비중']}\n\n- {item['핵심포인트']}")

    st.subheader("🏷️ 핵심키워드")
    render_keywords(result["핵심키워드"])

    st.subheader("✍️ 작성전략")
    strategy = result["작성전략"]
    st.markdown(f"<div class='soft'>{strategy['전체방향'].replace(chr(10), '<br>')}</div>", unsafe_allow_html=True)
    st.markdown("**섹션별 전략**")
    for i, item in enumerate(strategy["섹션별전략"], 1):
        with st.expander(f"{i}. {item['섹션']}", expanded=(i == 1)):
            st.write(item["전략"])
    st.markdown("**차별화포인트**")
    st.markdown(f"<div class='warn'>{strategy['차별화포인트'].replace(chr(10), '<br>')}</div>", unsafe_allow_html=True)

    st.subheader("💬 예상 질문 & 답변")
    for i, item in enumerate(result["예상QA"], 1):
        with st.expander(f"Q{i}. {item['질문']}", expanded=(i == 1)):
            st.write(item["답변"])

    st.subheader("📚 참고자료 · 유사과제 & 관련논문")
    st.info("현재는 Claude API와 웹 검색이 연결되지 않아 참고자료를 비워 둡니다.")

    st.subheader("📥 결과 저장")
    c1, c2 = st.columns(2)
    with c1:
        st.download_button("텍스트 결과 다운로드", data=st.session_state.copy_text, file_name="rfp_ai_demo_result.txt", mime="text/plain", use_container_width=True)
    with c2:
        st.download_button("JSON 결과 다운로드", data=json.dumps(result, ensure_ascii=False, indent=2), file_name="rfp_ai_demo_result.json", mime="application/json", use_container_width=True)

    with st.expander("복사용 텍스트 보기"):
        st.text_area("복사용 텍스트", value=st.session_state.copy_text, height=320, disabled=True, label_visibility="collapsed")
