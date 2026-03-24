# 코드 리뷰 Q&A

팀 리뷰 대비 예상 질문과 답변 모음.

---

## tools/changelog.py

**Q. read_changelog가 30줄 제한인데 프론트에서도 표기돼요?**
read_changelog 결과는 LLM을 거쳐 사용자에게 전달됨. "총 X줄 중 30줄 표시" 메시지가 그대로 나올 수도 있고 LLM이 생략할 수도 있어서 보장 안 됨. 프론트에서 직접 렌더링하지 않는 구조상 한계.

---

**Q. append_changelog 안에서 왜 Notion 동기화를 직접 호출해요?**
Notion 동기화를 에이전트가 별도로 기억하지 않아도 되게끔 의도적으로 묶은 것. changelog 기록과 Notion 동기화를 항상 함께 일어나는 하나의 작업으로 취급. NOTION_CHANGELOG_PAGE_ID 미설정 시 조용히 무시해서 Notion 없는 환경에서도 동작.

---

## tools/github_tools.py

**Q. create_issue / comment_on_issue는 HITL이 어디서 걸려요?**
오케스트레이터가 아닌 github 서브에이전트 레벨에서 interrupt_on으로 설정됨. 오케스트레이터 HITL(create_event 등)과 별개로 동작. 서브에이전트 자체에서 쓰기 작업을 차단하는 구조.

---

## storage/db.py

**Q. SQLite 실제로 써요?**
초기 설계에서 로컬 폴백용으로 넣었음. 지금은 로컬도 Neon PostgreSQL 씀. 제거 가능하지만 일단 유지 중.
