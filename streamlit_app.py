import json
import uuid
from typing import Any

import requests
import streamlit as st


st.set_page_config(
    page_title="Dify Lookbook Generator",
    page_icon="🎭",
    layout="centered",
)


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
    上传文件到 Dify /files/upload
    Dify 工作流文件上传接口要求:
    - multipart/form-data
    - file
    - user
    """
    files = {
        "file": (
            uploaded_file.name,
            uploaded_file.getvalue(),
            "application/pdf",
        )
    }
    data = {
        "user": user_id,
    }

    resp = requests.post(
        f"{DIFY_BASE_URL}/files/upload",
        headers=get_headers(),
        files=files,
        data=data,
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()


def run_workflow(upload_file_id: str, count: int, user_id: str) -> dict:
    """
    执行 Dify 工作流 /workflows/run

    这里假设你的开始节点里:
    - pdf_doc 是 File 类型（单文件）
    - count 是 Number 类型
    """
    payload = {
        "inputs": {
            "count": count,
            "pdf_doc": {
                "transfer_method": "local_file",
                "upload_file_id": upload_file_id,
                "type": "document",
            },
        },
        "response_mode": "blocking",
        "user": user_id,
    }

    resp = requests.post(
        f"{DIFY_BASE_URL}/workflows/run",
        headers={
            **get_headers(),
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=300,
    )
    resp.raise_for_status()
    return resp.json()


def pretty_json(data: Any):
    st.code(
        json.dumps(data, ensure_ascii=False, indent=2),
        language="json",
    )


def main():
    st.title("🎭 Dify Lookbook Generator")
    st.caption("上传 PDF Lookbook，调用 Dify 工作流生成角色图。")

    with st.expander("使用说明"):
        st.markdown(
            """
1. 上传一个 PDF Lookbook 文件  
2. 设置 `count` 数量  
3. 点击 **开始生成**  
4. 页面会先上传 PDF 到 Dify，再触发你的工作流  
5. 结果以 Dify 工作流返回为准
            """
        )

    if not DIFY_BASE_URL or not DIFY_API_KEY:
        st.error("缺少 Dify 配置。请先在 Streamlit Secrets 中填写 DIFY_BASE_URL 和 DIFY_API_KEY。")
        st.stop()

    uploaded_file = st.file_uploader(
        "上传 Lookbook PDF",
        type=["pdf"],
        accept_multiple_files=False,
    )

    count = st.number_input(
        "count",
        min_value=1,
        max_value=50,
        value=8,
        step=1,
    )

    if "streamlit_user_id" not in st.session_state:
        st.session_state["streamlit_user_id"] = f"streamlit-{uuid.uuid4().hex[:12]}"

    user_id = st.text_input(
        "当前会话 user_id",
        value=st.session_state["streamlit_user_id"],
        disabled=True,
    )

    if st.button("开始生成", use_container_width=True, type="primary"):
        if uploaded_file is None:
            st.error("请先上传 PDF 文件。")
            st.stop()

        try:
            with st.spinner("正在上传文件到 Dify..."):
                upload_result = upload_file_to_dify(uploaded_file, user_id)

            st.success("文件上传成功。")
            pretty_json(upload_result)

            upload_file_id = upload_result.get("id")
            if not upload_file_id:
                st.error("Dify 上传返回里没有拿到文件 id。")
                st.stop()

            with st.spinner("正在触发工作流..."):
                workflow_result = run_workflow(
                    upload_file_id=upload_file_id,
                    count=int(count),
                    user_id=user_id,
                )

            st.success("工作流触发成功。")
            pretty_json(workflow_result)

            data = workflow_result.get("data", {})
            outputs = data.get("outputs")

            if outputs is not None:
                st.subheader("工作流输出")
                pretty_json(outputs)

        except requests.HTTPError as e:
            st.error(f"HTTP 请求失败：{e}")
            try:
                st.code(e.response.text, language="json")
            except Exception:
                pass
        except Exception as e:
            st.error(f"运行失败：{e}")


if __name__ == "__main__":
    main()
