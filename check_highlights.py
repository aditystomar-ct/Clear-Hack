"""Check if comments have anchors."""
from google.oauth2 import service_account
from googleapiclient.discovery import build

DOC_ID = "1JjMRXBia6P5abDTYzOIQ1nkdEQ-Q1RT6kRS24QqTK3U"
CREDS_PATH = "/Users/aditya.tomar/Desktop/Clear-Hack/credentials.json"

creds = service_account.Credentials.from_service_account_file(
    CREDS_PATH, scopes=["https://www.googleapis.com/auth/drive"],
)
drive = build("drive", "v3", credentials=creds, cache_discovery=False)

resp = drive.comments().list(
    fileId=DOC_ID,
    fields="comments(id,content,anchor,quotedFileContent)",
    includeDeleted=False,
).execute()

comments = resp.get("comments", [])
print(f"Total comments: {len(comments)}\n")

for c in comments[:5]:
    content_preview = c.get("content", "")[:60]
    anchor = c.get("anchor", "NO ANCHOR")
    quoted = c.get("quotedFileContent", {}).get("value", "")[:80]
    print(f"  ID: {c['id']}")
    print(f"  Content: {content_preview!r}")
    print(f"  Anchor: {anchor}")
    print(f"  Quoted: {quoted!r}")
    print()
