import json
import uuid
from typing import Any

import requests
import streamlit as st


st.set_page_config(page_title="Dify Lookbook Generator", page_icon="🎭", layout="centered")


def get_secret(name: str, default: str = "") -> str:
    try:
        return st.secrets[name]
    except Exception:
        return default


DIFY_BASE_URL = get_secret("DIFY_BASE_URL", "").rstrip("/")
DIFY_API_KEY = get_secret("DIFY_API_KEY", "")


def get_headers() -> dict:
    return {
        "Authorization": f"Bearer {DIFY_API_KEY}",
    }


def upload_file_to_dify(uploaded_file, user_id: str) -> dict:
    """
    Dify: POST /files/upload
    """
    if not DIFY_BASE_URL or not DIFY_API_KEY:
        raise ValueError("缺少 DIFY_BASE_URL 或 DIFY_API_KEY secrets。")

    url = f"{DIFY_BASE_URL}/files/upload"

    file_bytes = uploaded_file.getvalue()
    mime_type = uploaded_file.type or "application/pdf"

    files = {
        "file": (uploaded_file.name, file_bytes, mime_type),
    }
    data = {
        "user": user_id,
    }

    resp = requests.post(
        url,
        headers=get_headers(),
        files=files,
        data=data,
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()


def run_workflow(file_id: str, user_id: str, count: int) -> dict:
    """
    Dify: POST /workflows/run
    这里默认你的工作流输入变量名是:
    - pdf_doc
    - count

    如果你在 Dify 的 Access API 里看到变量名不同，只改 inputs 这里即可。
    """
    if not DIFY_BASE_URL or not DIFY_API_KEY:
        raise ValueError("缺少 DIFY_BASE_URL 或 DIFY_API_KEY secrets。")

    url = f"{DIFY_BASE_URL}/workflows/run"

    payload = {
        "inputs": {
            "count": int(count),
            "pdf_doc": [
                {
                    "type": "document",
                    "transfer_method": "local_file",
                    "upload_file_id": file_id,
                }
            ],
        },
        "response_mode": "blocking",
        "user": user_id,
    }

    resp = requests.post(
        url,
        headers={
            **get_headers(),
            "Content-Type": "application/json",
        },
        data=json.dumps(payload),
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()


def extract_outputs(workflow_resp: dict) -> Any:
    """
    尽量把 Dify 返回的 outputs 提取出来显示
    """
    if not isinstance(workflow_resp, dict):
        return workflow_resp

    data = workflow_resp.get("data", {})
    if isinstance(data, dict) and "outputs" in data:
        return data.get("outputs")

    return workflow_resp


def try_extract_filenames(outputs: Any) -> list[str]:
    result = []

    def walk(x):
        if isinstance(x, dict):
            for k, v in x.items():
                if k.lower() in {"file_name", "filename"} and isinstance(v, str):
                    result.append(v)
                else:
                    walk(v)
        elif isinstance(x, list):
            for item in x:
                walk(item)

    walk(outputs)
    return result


st.title("🎭 Dify Lookbook Generator")
st.caption("上传 PDF Lookbook，调用 Dify 工作流生成角色图。")

with st.expander("使用说明", expanded=False):
    st.markdown(
        """
1. 上传一个 PDF 文件  
2. 设置生成数量 count  
3. 点击“开始生成”  
4. 页面会展示 Dify 返回结果  

**注意**  
- 需要在 Streamlit Secrets 中配置：
  - `DIFY_BASE_URL`
  - `DIFY_API_KEY`
- 本示例默认你的 Dify 工作流输入变量名为：
  - `pdf_doc`
  - `count`
        """
    )

uploaded_file = st.file_uploader(
    "上传 Lookbook PDF",
    type=["pdf"],
    accept_multiple_files=False,
)

count = st.number_input("count", min_value=1, max_value=100, value=8, step=1)

if "user_id" not in st.session_state:
    st.session_state.user_id = f"streamlit-{uuid.uuid4().hex[:12]}"

st.text_input("当前会话 user_id", value=st.session_state.user_id, disabled=True)

run_button = st.button("开始生成", type="primary", use_container_width=True)

if run_button:
    if not uploaded_file:
        st.error("请先上传 PDF。")
        st.stop()

    if not DIFY_BASE_URL or not DIFY_API_KEY:
        st.error("请先在 Streamlit Secrets 中配置 DIFY_BASE_URL 和 DIFY_API_KEY。")
        st.stop()

    user_id = st.session_state.user_id

    try:
        with st.spinner("正在上传文件到 Dify..."):
            upload_resp = upload_file_to_dify(uploaded_file, user_id)
            file_id = upload_resp["id"]

        st.success("文件上传成功。")
        st.json(upload_resp, expanded=False)

        with st.spinner("正在执行 Dify 工作流..."):
            workflow_resp = run_workflow(file_id, user_id, int(count))

        st.success("工作流执行完成。")

        st.subheader("工作流原始返回")
        st.json(workflow_resp, expanded=False)

        outputs = extract_outputs(workflow_resp)

        st.subheader("提取后的 outputs")
        st.json(outputs, expanded=True)

        filenames = try_extract_filenames(outputs)
        if filenames:
            st.subheader("识别到的文件名")
            for name in filenames:
                st.write(f"- {name}")

    except requests.HTTPError as e:
        body = ""
        try:
            body = e.response.text
        except Exception:
            pass
        st.error(f"HTTP 请求失败：{e}")
        if body:
            st.code(body)
    except Exception as e:
        st.exception(e)
