# Frontend (Milestones 22 + 24)

Next.js UI for BESCOM Bill Saver — **bill extract + confirm**, **VNM**, **GNM**, and **official-doc RAG**.

## Run

```bash
# Terminal 1 — API
cd ..
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload

# Terminal 2 — UI
cd frontend
copy .env.local.example .env.local
npm install
npm run dev
```

Open http://localhost:3000

API docs: http://127.0.0.1:8000/docs

After extract, if `needs_confirmation` is non-empty, the Bills tab shows a confirm form that calls `POST /bills/{analysis_id}/confirm`.
