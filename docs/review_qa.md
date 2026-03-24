# 코드 리뷰 Q&A

팀 리뷰 대비 예상 질문과 답변 모음.

---

## storage/db.py

**Q. SQLite 실제로 써요?**
초기 설계에서 로컬 폴백용으로 넣었음. 지금은 로컬도 Neon PostgreSQL 씀. 제거 가능하지만 일단 유지 중.
