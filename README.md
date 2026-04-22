# OmniVoice + MuseTalk Minimal Rebuild

This is a clean rebuild focused on a chunk-wise realtime pipeline:

- STT (audio upload) -> OpenAI transcription
- LLM streaming -> chunking
- OmniVoice TTS -> chunk WAV
- MuseTalk server worker -> chunk MP4
- FastAPI + WebSocket events -> frontend playback

## Preserved Assets

- Avatar: `static/core/avatar.mp4`
- Default voice reference: `omnivoice/audio(1).mp3`
- Model runtimes: `.models/` and `omnivoice/`

## Run

1. Ensure env vars in `.env` are valid (`OPENAI_API_KEY`, `MUSE_TALK_PYTHON`, `MUSE_TALK_DIR`).
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Start server:

```bash
python run.py
```

4. Open:

- `http://localhost:8000`

## Avatar Cache Prep

To precompute the MuseTalk avatar cache from a source video and regenerate:

```bash
python gen_muse.py --file static/core/avatar.mp4 --force
```

This creates the upstream-style cache artifacts under `.models/MuseTalk/results/v15/avatars/<avatar_id>/`:

- `full_imgs/`
- `mask/`
- `avator_info.json`
- `coords.pkl`
- `latents.pt`
- `mask_coords.pkl`

The script also writes `lip_boxes.pkl` for the optional `lip_mask` runtime compositor.

## API

- `GET /health`
- `POST /api/query` with `{ "text": "..." }`
- `POST /api/query/audio` multipart file field `audio`
- `WS /ws/session` send `{ "type": "user.text", "text": "..." }`

## Notes

- MuseTalk worker runs in persistent server mode for lower per-chunk overhead.
- Chunking is controlled by `LIPSYNC_CHUNK_MAX_CHARS` and `LIPSYNC_CHUNK_MAX_COUNT`.
- `MUSE_TALK_VIDEO_WRITE_MODE=direct_h264` keeps browser-safe final MP4s while avoiding PNG frame dumps when direct encoding is available.
- WebRTC signaling endpoint exists as a placeholder (`/api/webrtc/offer`) and can be extended to full aiortc flow.
