"""
Search-and-summarize demo with bring-your-own-key (BYOK).
 
The user pastes their own API key into the UI. It lives only in
st.session_state for the life of the browser session — it is never
written to disk, logged, or sent anywhere except the LLM provider.
"""
 
import streamlit as st
import anthropic  # swap for `openai` etc. if you use a different provider
 
st.set_page_config(page_title="Search & Summarize", page_icon="🔎")
st.title("🔎 Search & Summarize")
st.caption("Searches a few pages and summarizes the findings with an LLM.")
 
# --- API key: bring your own -------------------------------------------------
# password input masks the value; session_state keeps it in memory only.
api_key = st.text_input(
    "Your Anthropic API key",
    type="password",
    help="Your key is held in memory for this session only — never stored or logged.",
    value=st.session_state.get("api_key", ""),
)
if api_key:
    st.session_state["api_key"] = api_key
 
st.markdown(
    "Don't have a key? Get one at "
    "[console.anthropic.com](https://console.anthropic.com/). "
    "You're billed by your provider for your own usage."
)
 
# --- Your existing logic goes here ------------------------------------------
def search_pages(query: str) -> list[str]:
    """
    Replace this with your real search/fetch code.
    Should return a list of text blobs (one per page) to summarize.
    """
    # TODO: plug in your 5-page search + fetch logic
    return [f"(placeholder fetched content for: {query})"]
 
 
def summarize(pages: list[str], query: str, key: str) -> str:
    """Send the collected page text to the LLM and return a summary."""
    client = anthropic.Anthropic(api_key=key)
    joined = "\n\n---\n\n".join(pages)
    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": (
                f"Summarize the key findings about '{query}' from these "
                f"sources:\n\n{joined}"
            ),
        }],
    )
    # resp.content may hold several block types; keep only the text ones.
    return "".join(block.text for block in resp.content if block.type == "text")
 
 
# --- UI ----------------------------------------------------------------------
query = st.text_input("What do you want to search for?")
 
if st.button("Search", type="primary"):
    if not st.session_state.get("api_key"):
        st.error("Please enter your API key first.")
    elif not query.strip():
        st.error("Please enter something to search for.")
    else:
        try:
            with st.spinner("Searching pages…"):
                pages = search_pages(query)
            with st.spinner("Summarizing…"):
                summary = summarize(pages, query, st.session_state["api_key"])
            st.subheader("Summary")
            st.write(summary)
        except anthropic.AuthenticationError:
            st.error("That key was rejected. Double-check it and try again.")
        except Exception as e:  # keep the demo from crashing on edge cases
            st.error(f"Something went wrong: {e}")