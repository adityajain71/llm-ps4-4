"""Blog Post Generator (PS 4) - Streamlit + Google Gemini.

Takes a topic, a tone and a target word count, builds a structured prompt,
calls Gemini and shows a blog post (title, intro, sections, conclusion)
with a Markdown download button.
"""

import os
import re

import streamlit as st
from dotenv import load_dotenv
from google import genai
from google.genai import errors as genai_errors
from google.genai import types

load_dotenv()

# Primary model first; the others are fallbacks if it is busy or too slow.
MODELS = ["gemini-3.1-flash-lite", "gemini-3.5-flash", "gemini-3.8-flash"]
TIMEOUT_MS = 45_000  # give up on one model after 45 s and try the next

TONES = ["Professional", "Casual", "Friendly", "Informative", "Humorous", "Persuasive"]

SYSTEM_PROMPT = (
    "You are an experienced blog writer who helps students start writing blogs. "
    "You write clear, original, well-structured posts in Markdown."
)

PROMPT_TEMPLATE = """Write a complete blog post on the topic below.

Topic: {topic}
Tone: {tone}
Target length: about {words} words (stay within 10% of this).

Follow this structure exactly, in Markdown:
# <A catchy, specific title>

## Introduction
<One or two paragraphs that hook the reader and say what the post covers.>

## <Section heading 1>
<Body paragraphs. Use bullet points or a numbered list where it helps.>

## <Section heading 2>
...

(Use {sections} main sections in total, each with a meaningful heading - not "Section 1".)

## Conclusion
<Sum up the key points and end with a takeaway or call to action.>

Rules:
- Keep the {tone_lower} tone consistently from start to finish.
- Do not invent statistics, quotes or sources.
- Output only the blog post in Markdown, with no notes before or after it.
"""


def build_prompt(topic: str, tone: str, words: int) -> str:
    # More words -> more sections, so each section stays a readable length.
    sections = 3 if words <= 500 else 4 if words <= 1000 else 5
    return PROMPT_TEMPLATE.format(
        topic=topic.strip(), tone=tone, tone_lower=tone.lower(),
        words=words, sections=sections,
    )


def generate_blog(prompt: str, api_key: str) -> tuple[str, str]:
    """Call Gemini and return (markdown, model_used). Falls back if a model is busy."""
    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(
            timeout=TIMEOUT_MS,
            retry_options=types.HttpRetryOptions(attempts=1),  # we handle fallback ourselves
        ),
    )
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        temperature=0.8,
        # Blog writing doesn't need step-by-step reasoning; turning it off is much faster.
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    )
    last_error = None
    for model in MODELS:
        try:
            response = client.models.generate_content(
                model=model, contents=prompt, config=config,
            )
            return response.text.strip(), model
        except genai_errors.ClientError as e:
            if e.code == 429:  # rate-limited on this model -> try the next one
                last_error = e
                continue
            raise  # bad key / bad request: no point trying other models
        except Exception as e:  # 5xx, timeout, network hiccup -> try the next model
            last_error = e
    raise last_error


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "blog-post"


# ----------------------------- UI -----------------------------
st.set_page_config(page_title="Blog Post Generator", page_icon="📝", layout="centered")
st.title("📝 Blog Post Generator")
st.caption("Enter a topic, choose a tone and length, and get a structured blog post "
           "(title, introduction, sections, conclusion) written by Google Gemini.")

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    st.error("GEMINI_API_KEY is not set. Create a .env file with GEMINI_API_KEY=your_key "
             "(see .env.example).")
    st.stop()

with st.form("blog_form"):
    topic = st.text_input("Blog topic", placeholder="e.g. How to start learning Python in college")
    tone = st.selectbox("Tone", TONES)
    words = st.slider("Word count", min_value=300, max_value=1500, value=600, step=100)
    submitted = st.form_submit_button("Generate blog post", type="primary")

if submitted:
    if not topic.strip():
        st.warning("Please enter a topic.")
    else:
        with st.spinner("Writing your blog post..."):
            try:
                blog, model_used = generate_blog(build_prompt(topic, tone, words), api_key)
                st.session_state["blog"] = blog
                st.session_state["meta"] = (topic, tone, words, model_used)
            except Exception as e:
                st.error(f"Could not generate the blog post: {e}")

if "blog" in st.session_state:
    blog = st.session_state["blog"]
    topic_used, tone_used, words_used, model_used = st.session_state["meta"]
    actual = len(re.findall(r"\b\w+\b", blog))
    st.divider()
    st.caption(f"Tone: {tone_used} · Target: {words_used} words · "
               f"Generated: {actual} words · Model: {model_used}")
    st.markdown(blog)
    st.download_button(
        "⬇️ Download as Markdown (.md)",
        data=blog,
        file_name=f"{slugify(topic_used)}.md",
        mime="text/markdown",
    )
