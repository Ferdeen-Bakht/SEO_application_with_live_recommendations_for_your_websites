import streamlit as st
from seo_lab.config import DOTNET_BASE_URL
from seo_lab.dotnet_client import get_page, publish_page_seo
from seo_lab.repository import list_proposals, set_status, update_proposed
import httpx

st.title("3. Approval & publishing")
st.write("First edit or review a proposal, then approve it. Publishing is a separate button and only targets the local ASP.NET Core demo website.")
status_filter = st.selectbox("Show proposals", ["pending", "approved", "rejected", "published", "all"])
proposals = list_proposals(None if status_filter == "all" else status_filter)
if not proposals:
    st.info("No proposals in this status yet. Create one on the Content optimizer page.")
    st.stop()

labels = [f"#{p['id']} · {p['status'].upper()} · {p['page_path']} · {p['target_query']}" for p in proposals]
selected_label = st.selectbox("Select a proposal", labels)
proposal = proposals[labels.index(selected_label)]
original = proposal["original"]
proposed = proposal["proposed"]

st.caption(f"Page version at draft time: {proposal['original_version']} · Created: {proposal['created_at']}")
left, right = st.columns(2)
with left:
    st.subheader("Original content")
    st.write("**Title**", original.get("title", ""))
    st.write("**Meta description**", original.get("metaDescription", ""))
    st.write("**H1**", original.get("h1", ""))
    with st.expander("Original body"):
        for paragraph in original.get("paragraphs", []): st.write(paragraph)
with right:
    st.subheader("Proposed content (editable)")
    title = st.text_input("Title", value=proposed.get("title", ""), key=f"q_title_{proposal['id']}", max_chars=300)
    meta = st.text_area("Meta description", value=proposed.get("metaDescription", ""), key=f"q_meta_{proposal['id']}", max_chars=1000)
    h1 = st.text_input("H1", value=proposed.get("h1", ""), key=f"q_h1_{proposal['id']}", max_chars=300)
    body = st.text_area("Body (blank line between paragraphs)", value="\n\n".join(proposed.get("paragraphs", [])), key=f"q_body_{proposal['id']}", height=240, max_chars=12000)

with st.expander("AI rationale and target query"):
    st.write("**Target query:**", proposal["target_query"])
    st.write(proposal["rationale"] or "No rationale supplied.")

paragraphs = [p.strip() for p in body.split("\n\n") if p.strip()]
editable = {"title": title.strip(), "metaDescription": meta.strip(), "h1": h1.strip(), "paragraphs": paragraphs}

c1, c2, c3 = st.columns(3)
with c1:
    if st.button("Save edits", use_container_width=True, disabled=proposal["status"] != "pending"):
        if not title.strip() or not meta.strip() or not h1.strip() or len(paragraphs) < 1:
            st.error("Provide title, description, H1 and at least one paragraph.")
        elif update_proposed(proposal["id"], editable):
            st.success("Edits saved. Proposal remains pending.")
            st.rerun()
        else:
            st.error("Proposal status changed. Refresh and try again.")
with c2:
    if st.button("Approve proposal", type="primary", use_container_width=True, disabled=proposal["status"] != "pending"):
        if not title.strip() or not meta.strip() or not h1.strip() or len(paragraphs) < 1:
            st.error("Make sure the proposal is complete before approving.")
        else:
            update_proposed(proposal["id"], editable)
            if set_status(proposal["id"], "approved", "pending"):
                st.success("Approved. The live test site has not changed yet.")
                st.rerun()
            else:
                st.error("Could not approve; refresh the page.")
with c3:
    if st.button("Reject proposal", use_container_width=True, disabled=proposal["status"] != "pending"):
        if set_status(proposal["id"], "rejected", "pending"):
            st.success("Proposal rejected.")
            st.rerun()
        else:
            st.error("Could not reject; refresh the page.")

if proposal["status"] == "approved":
    st.warning("This proposal is approved but not published. Publishing will change the local .NET demo site's stored title, description, H1 and body.")
    if st.button("Publish approved content to local .NET demo", type="primary"):
        try:
            current_page = get_page(proposal["slug"])
            if int(current_page.get("version", 0)) != int(proposal["original_version"]):
                st.error("The page changed after this proposal was created. Do not overwrite newer content; create a fresh audit and proposal.")
            else:
                result = publish_page_seo(proposal["slug"], {
                    **proposed,
                    "expectedVersion": int(proposal["original_version"]),
                    "approvalId": int(proposal["id"]),
                }, base_url=proposal["site_url"])
                if set_status(proposal["id"], "published", "approved"):
                    st.success(f"Published to the local demo site. New page version: {result['page']['version']}.")
                    st.link_button("Open updated page", f"{proposal['site_url'].rstrip('/')}{proposal['page_path']}")
                    st.rerun()
                else:
                    st.error("The site was updated but local proposal status could not be marked published. Inspect the page and database before retrying.")
        except httpx.HTTPStatusError as exc:
            st.error(f"Publishing API returned HTTP {exc.response.status_code}: {exc.response.text}")
        except Exception as exc:
            st.error(f"Publish failed: {exc}")

if proposal["status"] == "published":
    st.success("This proposal has been published to the local demo site.")
    st.link_button("Open updated page", f"{proposal['site_url'].rstrip('/')}{proposal['page_path']}")

st.caption("Safety check: publishing is not enabled for arbitrary sites. The included adapter only calls the local .NET demo API, which checks an API key and page version.")
