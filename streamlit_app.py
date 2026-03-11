import json
import threading
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


# 这里优先读 Streamlit secrets
# 如果没配 secrets，就使用默认值
DIFY_BASE_URL = get_secret("DIFY_BASE_URL", "https://api.dify.ai/v1").rstrip("/")
DIFY_API_KEY = get_secret("DIFY_API_KEY", "")
GOOGLE_DRIVE_URL = get_secret(
    "GOOGLE_DRIVE_URL",
    "https://drive.google.com/drive/u/0/folders/1PjQpJhyTXJEcJmjpTDSoJ1FpFA0n8pHV?hl=zh-TW",
)


def get_headers() -> dict:
    return {
        "Authorization": f"Bearer {DIFY_API_KEY}",
    }


def upload_file_to_dify(uploaded_file, user_id: str) -> dict:
    """
    第一步：上传文件到 Dify
    """
    file_bytes = uploaded_file.getvalue()

    files = {
        "file": (uploaded_file.name, file_bytes, "application/pdf")
    }
    data = {
        "user": user_id
    }

    resp = requests.post(
        f"{DIFY_BASE_URL}/files/upload",
        headers=get_headers(),
        files=files,
        data=data,
        timeout=(20, 120),
    )
    resp.raise_for_status()
    return resp.json()


def _run_workflow_in_background(upload_file_id: str, count: int, user_id: str) -> None:
    """
    第二步：后台触发 Dify workflow
    这里故意不把执行结果返回给前端页面。
    页面只负责“提交任务”，不等待最终结果。
    """
    payload = {
        "inputs": {
            "pdf_doc": {
                "transfer_method": "local_file",
                "upload_file_id": upload_file_id,
                "type": "document",
            },
            "count": count,
        },
        "response_mode": "blocking",
        "user": user_id,
    }

    try:
        # 放到后台线程里执行，前端页面不等待
        resp = requests.post(
            f"{DIFY_BASE_URL}/workflows/run",
            headers={
                **get_headers(),
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=(10, 180),
        )

        # 即便这里返回 504，也有可能工作流已经被提交并继续跑了
        # 所以这里只记录，不把异常抛回前端
        try:
            _ = resp.text
        except Exception:
            pass

    except Exception:
        # 后台静默处理，不阻塞前端
        pass


def trigger_workflow_async(upload_file_id: str, count: int, user_id: str) -> None:
    t = threading.Thread(
        target=_run_workflow_in_background,
        args=(upload_file_id, count, user_id),
        daemon=True,
    )
    t.start()


def init_session():
    if "user_id" not in st.session_state:
        st.session_state.user_id = f"streamlit-{uuid.uuid4().hex[:12]}"


def main():
    init_session()

    st.title("🎭 Dify Lookbook Generator")
    st.caption("上传 PDF Lookbook，调用 Dify 工作流生成角色图。")

    with st.expander("使用说明", expanded=False):
        st.markdown(
            """
1. 上传角色设定 PDF  
2. 选择 count 数量  
3. 点击 **开始生成**  
4. 页面只负责提交任务，不等待最终出图  
5. 生成完成后，请到你的 Google Drive 文件夹中查看结果
"""
        )

    uploaded_file = st.file_uploader(
        "上传 Lookbook PDF",
        type=["pdf"],
        accept_multiple_files=False,
    )

    count = st.number_input(
        "count",
        min_value=1,
        max_value=20,
        value=8,
        step=1,
    )

    st.text_input(
        "当前会话 user_id",
        value=st.session_state.user_id,
        disabled=True,
    )

    if st.button("开始生成", use_container_width=True):
        if not DIFY_API_KEY:
            st.error("未检测到 DIFY_API_KEY，请先在 Streamlit secrets 中配置。")
            return

        if not uploaded_file:
            st.error("请先上传 PDF 文件。")
            return

        try:
            # 1) 同步上传文件
            upload_result = upload_file_to_dify(uploaded_file, st.session_state.user_id)

            st.success("文件上传成功，任务已提交。")
            st.json(upload_result)

            upload_file_id = upload_result.get("id", "")
            if not upload_file_id:
                st.error("文件上传成功，但未拿到 upload_file_id，无法继续触发工作流。")
                return

            # 2) 后台异步触发 workflow
            trigger_workflow_async(
                upload_file_id=upload_file_id,
                count=int(count),
                user_id=st.session_state.user_id,
            )

            # 3) 立即告诉用户去 Google Drive 查看
            st.info(
                "请耐心等待后到您的谷歌硬盘中查看生成内容"
            )
            st.markdown(
                f"[打开谷歌硬盘查看结果]({GOOGLE_DRIVE_URL})"
            )
            st.code(
                "请耐心等待后到您的谷歌硬盘中查看生成内容\n"
                f"{GOOGLE_DRIVE_URL}",
                language="text",
            )

        except requests.HTTPError as e:
            detail = ""
            try:
                detail = e.response.text
            except Exception:
                detail = str(e)

            st.error(f"HTTP 请求失败：{e}")
            if detail:
                st.code(detail, language="json")

        except Exception as e:
            st.error(f"发生异常：{e}")


if __name__ == "__main__":
    main()
