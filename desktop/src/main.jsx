import React, { useEffect, useState, useMemo, useRef } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

const API = "http://127.0.0.1:8787";

const PIPELINE_STEPS = [
  { key: "download", label: "1. Tải Video", icon: "📥" },
  { key: "extract_audio", label: "2. Tách Âm Thanh", icon: "🎵" },
  { key: "transcribe", label: "3. Whisper AI", icon: "🎙️" },
  { key: "translate", label: "4. Dịch Thuật", icon: "🌐" },
  { key: "tts", label: "5. Lồng Tiếng AI", icon: "🗣️" },
  { key: "mix_and_render", label: "6. Xuất Video", icon: "🎬" },
];

function App() {
  const [url, setUrl] = useState("");
  const [sourceLanguage, setSourceLanguage] = useState("auto");
  const [targetLanguage, setTargetLanguage] = useState("vi");
  const [voiceId, setVoiceId] = useState("vieneu:ngoc_huyen");
  const [voices, setVoices] = useState([]);
  const [job, setJob] = useState(null);
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  const timerRef = useRef(null);

  useEffect(() => {
    fetch(`${API}/api/voices`)
      .then(r => r.json())
      .then(data => {
        setVoices(data);
        if (data.length > 0 && !voiceId) {
          const defaultVi = data.find(v => v.id === "vieneu:ngoc_huyen") || data[0];
          setVoiceId(defaultVi.id);
        }
      })
      .catch(() => {});
  }, []);

  const jobId = job?.id || job?.job_id;
  const isRunning = job?.status === "running" || job?.status === "queued" || isSubmitting;

  // Elapsed timer tracking
  useEffect(() => {
    if (isRunning) {
      const start = Date.now() - (elapsedSeconds * 1000);
      timerRef.current = setInterval(() => {
        setElapsedSeconds(Math.floor((Date.now() - start) / 1000));
      }, 1000);
    } else {
      if (timerRef.current) clearInterval(timerRef.current);
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [isRunning]);

  // Polling job status
  useEffect(() => {
    if (!jobId) return;

    const pollInterval = setInterval(async () => {
      try {
        const response = await fetch(`${API}/api/jobs/${jobId}`);
        if (!response.ok) return;
        const data = await response.json();
        setJob(data);

        if (data.status === "completed" || data.status === "failed") {
          clearInterval(pollInterval);
        }
      } catch {
        // ignore network hiccups
      }
    }, 1000);

    return () => clearInterval(pollInterval);
  }, [jobId]);

  async function processVideo() {
    setError("");
    setJob(null);
    setElapsedSeconds(0);

    if (!url.trim()) {
      setError("Vui lòng dán liên kết video (Douyin, TikTok, YouTube...).");
      return;
    }

    setIsSubmitting(true);

    try {
      const response = await fetch(`${API}/api/jobs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url: url.trim(),
          source_language: sourceLanguage,
          target_language: targetLanguage,
          voice_id: voiceId || null,
          rewrite: false
        })
      });

      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Không thể tạo tác vụ.");
      setJob(data);
    } catch (e) {
      setError(e.message);
    } finally {
      setIsSubmitting(false);
    }
  }

  const groupedVoices = useMemo(() => {
    const groups = {};
    for (const v of voices) {
      const cat = v.category || (v.id.startsWith("vieneu:") ? "VieNeu AI" : v.id.startsWith("vi-VN-") || v.id.startsWith("en-US-") ? "Edge Neural" : v.id.startsWith("gtts") ? "Google AI" : "Local OS");
      if (!groups[cat]) groups[cat] = [];
      groups[cat].push(v);
    }
    return groups;
  }, [voices]);

  const progress = job?.progress ?? (isSubmitting ? 3 : 0);

  const stageLabels = {
    queued: "Đang xếp hàng khởi tạo...",
    download: "Đang tải video gốc độ nét cao...",
    extract_audio: "Đang trích xuất luồng âm thanh...",
    transcribe: "Đang nhận diện giọng nói (Faster-Whisper AI)...",
    translate: "Đang dịch thuật phụ đề chính xác...",
    tts: "Đang tạo giọng đọc lồng tiếng AI (VieNeu-TTS / Edge-TTS)...",
    mix_and_render: "Đang ghép âm thanh và xuất video MP4...",
    done: "Đã hoàn thành xuất sắc 100%!",
    error: "Xảy ra lỗi trong quá trình xử lý"
  };

  const currentStage = isSubmitting ? "queued" : (job?.stage || "");

  const formatTimer = (secs) => {
    const m = Math.floor(secs / 60).toString().padStart(2, "0");
    const s = (secs % 60).toString().padStart(2, "0");
    return `${m}:${s}`;
  };

  const getStepStatus = (stepKey, index) => {
    if (!job) return "";
    if (job.status === "completed") return "completed";
    
    const stageOrder = ["download", "extract_audio", "transcribe", "translate", "tts", "mix_and_render"];
    const curIdx = stageOrder.indexOf(job.stage);
    if (curIdx === -1) return "";
    if (index < curIdx) return "completed";
    if (index === curIdx) return "active";
    return "";
  };

  return (
    <main className="page">
      <section className="hero">
        <div>
          <div className="badge">
            <span className="badge-dot" />
            AI VIDEO DUBBER & DỊCH THUẬT TỰ ĐỘNG
          </div>
          <h1>Dán link video.<br />Tạo video lồng tiếng AI.</h1>
          <p>Tải video Douyin/TikTok/YouTube → Tự động nhận diện → Dịch thuật chuẩn xác → Lồng tiếng AI (Ngọc Huyền v2, Hoài My, Google...) → Xuất video MP4 & Phụ đề SRT.</p>
        </div>
      </section>

      <section className="card">
        <label>Đường dẫn Video (Douyin, TikTok, YouTube...)</label>
        <div className="url-row">
          <input
            value={url}
            onChange={e => setUrl(e.target.value)}
            placeholder="https://www.douyin.com/video/... hoặc https://www.youtube.com/watch?v=..."
            disabled={isRunning}
            onKeyDown={e => { if (e.key === "Enter" && !isRunning) processVideo(); }}
          />
          <button
            className={`primary-btn ${isRunning ? "loading" : ""}`}
            onClick={processVideo}
            disabled={isRunning}
          >
            {isRunning ? (
              <>
                <div className="spinner" />
                <span>{isSubmitting ? "Đang gửi..." : "Đang xử lý..."}</span>
              </>
            ) : (
              <>
                <span>🚀 BẮT ĐẦU XỬ LÝ</span>
              </>
            )}
          </button>
        </div>

        <div className="grid">
          <div>
            <label>Ngôn ngữ nguồn</label>
            <select
              value={sourceLanguage}
              onChange={e => setSourceLanguage(e.target.value)}
              disabled={isRunning}
            >
              <option value="auto">Tự động nhận diện (Auto)</option>
              <option value="zh">Tiếng Trung (Chinese)</option>
              <option value="en">Tiếng Anh (English)</option>
              <option value="ja">Tiếng Nhật (Japanese)</option>
              <option value="ko">Tiếng Hàn (Korean)</option>
              <option value="vi">Tiếng Việt (Vietnamese)</option>
            </select>
          </div>

          <div>
            <label>Ngôn ngữ đích</label>
            <select
              value={targetLanguage}
              onChange={e => setTargetLanguage(e.target.value)}
              disabled={isRunning}
            >
              <option value="vi">Tiếng Việt (Vietnamese)</option>
              <option value="en">Tiếng Anh (English)</option>
              <option value="zh">Tiếng Trung (Chinese)</option>
              <option value="ja">Tiếng Nhật (Japanese)</option>
              <option value="ko">Tiếng Hàn (Korean)</option>
            </select>
          </div>

          <div>
            <label>Giọng đọc lồng tiếng (TTS)</label>
            <select
              value={voiceId}
              onChange={e => setVoiceId(e.target.value)}
              disabled={isRunning}
            >
              {Object.entries(groupedVoices).map(([cat, list]) => (
                <optgroup label={`─── ${cat} ───`} key={cat}>
                  {list.map(v => (
                    <option value={v.id} key={v.id}>
                      {v.name}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
          </div>
        </div>

        <div className="options">
          <div className="option">
            <strong>✓ Xử lý cục bộ đa luồng</strong>
            <span>Whisper AI và VieNeu-TTS chạy trực tiếp không giới hạn ký tự.</span>
          </div>
          <div className="option">
            <strong>✓ Giữ âm thanh nền</strong>
            <span>Tự động cân bằng và mix nhạc nền gốc với giọng đọc lồng tiếng.</span>
          </div>
          <div className="option">
            <strong>✓ Hỗ trợ phụ đề SRT</strong>
            <span>Tự động tạo file phụ đề .srt chính xác từng giây để gắn vào video.</span>
          </div>
        </div>

        {(job || isSubmitting) && (
          <div className="progress-card">
            <div className="progress-header">
              <div className="stage-title">
                {job?.status !== "completed" && job?.status !== "failed" && (
                  <span className="stage-pulse" />
                )}
                <span>{stageLabels[currentStage] || currentStage}</span>
              </div>
              <div className="progress-meta">
                <span className="timer">⏱️ {formatTimer(elapsedSeconds)}</span>
                <span className="percent-text">{progress}%</span>
              </div>
            </div>

            <div className="progress-track">
              <div
                className={`progress-fill ${isRunning ? "animated" : ""}`}
                style={{ width: `${Math.max(progress, isSubmitting ? 5 : 0)}%` }}
              />
            </div>

            <div className="pipeline-steps">
              {PIPELINE_STEPS.map((step, idx) => {
                const status = getStepStatus(step.key, idx);
                return (
                  <div className={`step-chip ${status}`} key={step.key}>
                    {status === "completed" ? "✓ " : `${step.icon} `}
                    {step.label}
                  </div>
                );
              })}
            </div>

            {job?.status === "completed" && jobId && (
              <div className="download-actions">
                <a
                  className="download-btn primary"
                  href={`${API}/api/jobs/${jobId}/download`}
                  target="_blank"
                  rel="noreferrer"
                >
                  🎬 Tải Video Hoàn Thành (.mp4)
                </a>
                <a
                  className="download-btn"
                  href={`${API}/api/jobs/${jobId}/subtitles`}
                  target="_blank"
                  rel="noreferrer"
                >
                  📝 Tải Tệp Phụ Đề (.srt)
                </a>
              </div>
            )}

            {job?.status === "failed" && (
              <pre className="error">{job.error}</pre>
            )}
          </div>
        )}

        {error && <div className="error">{error}</div>}
      </section>
    </main>
  );
}

createRoot(document.getElementById("root")).render(<App />);
