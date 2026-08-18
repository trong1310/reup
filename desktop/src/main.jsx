import React, { useEffect, useState, useMemo, useRef } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";
import ApiKeyModal from "./ApiKeyModal";

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
  const [activeTab, setActiveTab] = useState("product"); // "product" | "reup"
  
  // Reup state
  const [url, setUrl] = useState("");
  const [sourceLanguage, setSourceLanguage] = useState("auto");
  const [targetLanguage, setTargetLanguage] = useState("vi");
  const [voiceId, setVoiceId] = useState("vieneu:ngoc_huyen");
  const [voices, setVoices] = useState([]);
  const [job, setJob] = useState(null);
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [isApiModalOpen, setIsApiModalOpen] = useState(false);
  const [apiSettings, setApiSettings] = useState(null);

  // Product Render Video state
  const [productInputType, setProductInputType] = useState("file"); // "file" | "url"
  const [productImageUrl, setProductImageUrl] = useState("");
  const [productImageBase64, setProductImageBase64] = useState("");
  const [productImagePreview, setProductImagePreview] = useState("");
  const [productName, setProductName] = useState("");
  const [productPrompt, setProductPrompt] = useState("");
  const [videoCount, setVideoCount] = useState(1);
  const [genderOption, setGenderOption] = useState("female"); // "female" | "male"
  const [characterTypeOption, setCharacterTypeOption] = useState("real"); // "real" | "anime"
  const [productVoiceId, setProductVoiceId] = useState("vieneu:ngoc_huyen");
  
  const [productBatch, setProductBatch] = useState(null); // { batch_id, job_ids, count }
  const [productJobs, setProductJobs] = useState([]); // List of job status objects
  const [isProductSubmitting, setIsProductSubmitting] = useState(false);

  const timerRef = useRef(null);

  const loadVoices = () => {
    fetch(`${API}/api/voices`)
      .then(r => r.json())
      .then(data => {
        setVoices(data);
        if (data.length > 0 && !voiceId) {
          const defaultVi = data.find(v => v.id === "vieneu:ngoc_huyen") || data[0];
          setVoiceId(defaultVi.id);
          setProductVoiceId(defaultVi.id);
        }
      })
      .catch(() => {});
  };

  const loadSettings = () => {
    fetch(`${API}/api/settings`)
      .then(r => r.json())
      .then(data => {
        setApiSettings(data);
      })
      .catch(() => {});
  };

  useEffect(() => {
    loadVoices();
    loadSettings();
  }, []);

  const jobId = job?.id || job?.job_id;
  const isRunning = job?.status === "running" || job?.status === "queued" || isSubmitting;

  // Elapsed timer tracking for Reup
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

  // Polling Reup job status
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
        // ignore
      }
    }, 1000);

    return () => clearInterval(pollInterval);
  }, [jobId]);

  // Polling Product Jobs status
  useEffect(() => {
    if (!productBatch?.job_ids?.length) return;

    const pollInterval = setInterval(async () => {
      try {
        const updatedList = await Promise.all(
          productBatch.job_ids.map(async (id) => {
            const r = await fetch(`${API}/api/jobs/${id}`);
            if (r.ok) return await r.json();
            return { id, status: "queued", progress: 0 };
          })
        );
        setProductJobs(updatedList);

        const allFinished = updatedList.every(
          (j) => j.status === "completed" || j.status === "failed"
        );
        if (allFinished) {
          clearInterval(pollInterval);
        }
      } catch {
        // ignore
      }
    }, 1000);

    return () => clearInterval(pollInterval);
  }, [productBatch]);

  const handleFileUpload = (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (evt) => {
      setProductImageBase64(evt.target.result);
      setProductImagePreview(evt.target.result);
    };
    reader.readAsDataURL(file);
  };

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

  async function processProductVideoRender() {
    setError("");
    setProductBatch(null);
    setProductJobs([]);

    if (productInputType === "file" && !productImageBase64) {
      setError("Vui lòng tải lên ảnh sản phẩm.");
      return;
    }
    if (productInputType === "url" && !productImageUrl.trim()) {
      setError("Vui lòng nhập đường dẫn hoặc link sản phẩm từ TikTok / Web.");
      return;
    }

    setIsProductSubmitting(true);

    try {
      const response = await fetch(`${API}/api/product-jobs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          product_image_url: productInputType === "url" ? productImageUrl.trim() : null,
          product_image_base64: productInputType === "file" ? productImageBase64 : null,
          product_name: productName,
          prompt: productPrompt,
          count: parseInt(videoCount, 10) || 1,
          gender: genderOption,
          character_type: characterTypeOption,
          voice_id: productVoiceId || null
        })
      });

      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Không thể tạo tác vụ render.");
      setProductBatch(data);
    } catch (e) {
      setError(e.message);
    } finally {
      setIsProductSubmitting(false);
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
    download_image: "Đang xử lý hình ảnh sản phẩm...",
    generate_script: "AI đang suy nghĩ và sáng tạo kịch bản kịch tính...",
    extract_audio: "Đang trích xuất luồng âm thanh...",
    transcribe: "Đang nhận diện giọng nói (Faster-Whisper AI)...",
    translate: "Đang dịch thuật phụ đề chính xác...",
    tts: "Đang tạo giọng đọc lồng tiếng AI (VieNeu-TTS / Edge-TTS)...",
    mix_and_render: "Đang dựng hiệu ứng ZoomPan 20-25s và ghép phụ đề...",
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

  const activeApisCount = useMemo(() => {
    if (!apiSettings) return 0;
    let count = 0;
    if (apiSettings.has_groq) count++;
    if (apiSettings.has_gemini) count++;
    if (apiSettings.has_openai) count++;
    if (apiSettings.has_elevenlabs) count++;
    if (apiSettings.has_hf) count++;
    return count;
  }, [apiSettings]);

  const activeProviderLabels = useMemo(() => {
    if (!apiSettings) return [];
    const list = [];
    if (apiSettings.has_groq) list.push("Groq 1s");
    if (apiSettings.has_gemini) list.push("Gemini Flash");
    if (apiSettings.has_openai) list.push("OpenAI");
    if (apiSettings.has_elevenlabs) list.push("ElevenLabs");
    return list;
  }, [apiSettings]);

  return (
    <div className="app-container">
      {/* Sidebar Navigation */}
      <aside className="sidebar">
        <div className="sidebar-brand">
          <div className="sidebar-logo">⚡</div>
          <div className="sidebar-brand-text">
            <span className="brand-title">AI VIDEO STUDIO</span>
            <span className="brand-subtitle">PRO CREATOR v2.5</span>
          </div>
        </div>

        <nav className="nav-menu">
          <button
            className={`nav-item ${activeTab === "product" ? "active" : ""}`}
            onClick={() => setActiveTab("product")}
          >
            <span className="nav-icon">🛍️</span>
            <div className="nav-text">
              <span className="nav-label">Render Video Sản Phẩm</span>
              <span className="nav-desc">Tạo video AI từ ảnh TikTok</span>
            </div>
          </button>

          <button
            className={`nav-item ${activeTab === "reup" ? "active" : ""}`}
            onClick={() => setActiveTab("reup")}
          >
            <span className="nav-icon">🎬</span>
            <div className="nav-text">
              <span className="nav-label">Reup Video AI</span>
              <span className="nav-desc">Dịch & Lồng tiếng Douyin/TikTok</span>
            </div>
          </button>
        </nav>

        <div className="sidebar-footer">
          <button
            className="sidebar-api-btn"
            onClick={() => setIsApiModalOpen(true)}
          >
            <span className="api-icon">⚙️</span>
            <span>Cấu Hình API Cloud</span>
          </button>
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="main-content">
        <header className="top-header">
          <div className="header-title-group">
            <h2>{activeTab === "product" ? "🛒 TỰ ĐỘNG RENDER VIDEO SẢN PHẨM AI" : "🌐 REUP & DỊCH THUẬT LỒNG TIẾNG VIDEO"}</h2>
            <p>
              {activeTab === "product" 
                ? "Tự động phân tích ảnh sản phẩm, tự nghĩ kịch bản viral và render hàng loạt video 20-25s chất lượng 4K"
                : "Tự động tải video Douyin/TikTok, trích xuất âm thanh, dịch thuật siêu chuẩn và lồng tiếng AI cao cấp"}
            </p>
          </div>

          <button
            className="api-status-badge"
            onClick={() => setIsApiModalOpen(true)}
          >
            <span className="status-dot" />
            <span>{activeApisCount > 0 ? `${activeApisCount} API Active (${activeProviderLabels.join(", ")})` : "Local CPU Engine"}</span>
          </button>
        </header>

        {activeTab === "product" && (
          <div className="tab-content">
            <section className="card">
              <div className="form-group-title">
                <span className="step-num">1</span>
                <h3>Nguồn Ảnh & Thông Tin Sản Phẩm</h3>
              </div>

              <div className="input-type-switch">
                <button
                  className={`switch-btn ${productInputType === "file" ? "active" : ""}`}
                  onClick={() => setProductInputType("file")}
                >
                  📁 Upload Ảnh Sản Phẩm
                </button>
                <button
                  className={`switch-btn ${productInputType === "url" ? "active" : ""}`}
                  onClick={() => setProductInputType("url")}
                >
                  🔗 Dán Link Sản Phẩm TikTok / Web
                </button>
              </div>

              {productInputType === "file" ? (
                <div className="upload-dropzone">
                  <input
                    type="file"
                    accept="image/*"
                    onChange={handleFileUpload}
                    id="product-file-input"
                    className="file-input-hidden"
                  />
                  <label htmlFor="product-file-input" className="dropzone-label">
                    {productImagePreview ? (
                      <div className="image-preview-box">
                        <img src={productImagePreview} alt="Preview" />
                        <span className="change-img-text">🔄 Bấm để thay đổi ảnh</span>
                      </div>
                    ) : (
                      <div className="dropzone-placeholder">
                        <span className="upload-icon">📸</span>
                        <strong>Tải lên ảnh sản phẩm của bạn</strong>
                        <span>Hỗ trợ JPG, PNG, WEBP độ phân giải cao</span>
                      </div>
                    )}
                  </label>
                </div>
              ) : (
                <div className="url-input-box">
                  <label>Đường dẫn link sản phẩm (TikTok Shop, Shopee, Douyin...)</label>
                  <input
                    type="text"
                    value={productImageUrl}
                    onChange={(e) => {
                      setProductImageUrl(e.target.value);
                      if (e.target.value.startsWith("http")) setProductImagePreview(e.target.value);
                    }}
                    placeholder="https://vt.tiktok.com/... hoặc https://shopee.vn/..."
                  />
                </div>
              )}

              <div className="grid-2col">
                <div>
                  <label>Tên Sản Phẩm (Nên nhập rõ ràng)</label>
                  <input
                    type="text"
                    value={productName}
                    onChange={(e) => setProductName(e.target.value)}
                    placeholder="Ví dụ: Kem dưỡng da serum B5, Áo thun nam Polo..."
                  />
                </div>

                <div>
                  <label>Số Lượng Video Cần Render (Batch)</label>
                  <input
                    type="number"
                    min="1"
                    max="20"
                    value={videoCount}
                    onChange={(e) => setVideoCount(e.target.value)}
                  />
                </div>
              </div>

              <div className="form-group-title margin-top">
                <span className="step-num">2</span>
                <h3>Tùy Chọn Nhân Vật AI & Kịch Bản</h3>
              </div>

              <div className="options-grid">
                <div className="option-box">
                  <label>Giới Tính Giọng Đọc</label>
                  <div className="radio-group">
                    <button
                      className={`radio-btn ${genderOption === "female" ? "selected" : ""}`}
                      onClick={() => setGenderOption("female")}
                    >
                      👩 Giọng Nữ
                    </button>
                    <button
                      className={`radio-btn ${genderOption === "male" ? "selected" : ""}`}
                      onClick={() => setGenderOption("male")}
                    >
                      👨 Giọng Nam
                    </button>
                  </div>
                </div>

                <div className="option-box">
                  <label>Hình Hình Nhân Vật / Phong Cách</label>
                  <div className="radio-group">
                    <button
                      className={`radio-btn ${characterTypeOption === "real" ? "selected" : ""}`}
                      onClick={() => setCharacterTypeOption("real")}
                    >
                      🧍 Người Thật
                    </button>
                    <button
                      className={`radio-btn ${characterTypeOption === "anime" ? "selected" : ""}`}
                      onClick={() => setCharacterTypeOption("anime")}
                    >
                      🎨 Hoạt Hình / Anime
                    </button>
                  </div>
                </div>
              </div>

              <div className="margin-top-sm">
                <label>Kịch Bản / Prompt Nội Dung (Nếu bỏ trống AI sẽ tự suy nghĩ ngẫu nhiên kịch bản viral)</label>
                <textarea
                  rows="3"
                  value={productPrompt}
                  onChange={(e) => setProductPrompt(e.target.value)}
                  placeholder="Nhập ý tưởng kịch bản... Hoặc bỏ trống để AI tự tạo kịch bản hấp dẫn 20-25 giây!"
                />
              </div>

              <div className="margin-top-sm">
                <label>Giọng Đọc AI Cao Cấp</label>
                <select
                  value={productVoiceId}
                  onChange={(e) => setProductVoiceId(e.target.value)}
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

              <button
                className={`primary-btn full-width margin-top ${isProductSubmitting ? "loading" : ""}`}
                onClick={processProductVideoRender}
                disabled={isProductSubmitting}
              >
                {isProductSubmitting ? (
                  <>
                    <div className="spinner" />
                    <span>Đang khởi tạo các luồng render AI...</span>
                  </>
                ) : (
                  <span>🎬 RENDER NGAY {videoCount} VIDEO SẢN PHẨM AI (20-25 Giây)</span>
                )}
              </button>

              {error && <div className="error">{error}</div>}
            </section>

            {/* Batch Progress Video Grid Cards */}
            {productBatch && (
              <section className="card margin-top">
                <div className="batch-header">
                  <h3>🚀 Danh Sách Video Render AI ({productJobs.filter(j => j.status === 'completed').length} / {productBatch.count} Video Hoàn Thành)</h3>
                </div>

                <div className="video-card-grid">
                  {productJobs.map((j, idx) => (
                    <div className="video-preview-card" key={j.id || idx}>
                      <div className="card-video-box">
                        {j.status === "completed" ? (
                          <video
                            controls
                            preload="metadata"
                            src={`${API}/api/jobs/${j.id}/download`}
                            poster={productImagePreview || undefined}
                          />
                        ) : (
                          <div className="video-loading-placeholder">
                            <div className="spinner" />
                            <span className="placeholder-stage">{stageLabels[j.stage] || j.stage || "Đang render..."}</span>
                            <span className="placeholder-percent">{j.progress || 0}%</span>
                          </div>
                        )}
                      </div>

                      <div className="card-body">
                        <div className="card-header-info">
                          <span className="video-title">🎬 Video AI #{idx + 1}</span>
                          <span className={`status-badge ${j.status}`}>
                            {j.status === "completed" ? "✓ Hoàn thành" : j.status === "failed" ? "❌ Lỗi" : "⚡ Đang chạy"}
                          </span>
                        </div>

                        <div className="progress-track sm">
                          <div
                            className={`progress-fill ${j.status !== "completed" ? "animated" : ""}`}
                            style={{ width: `${j.progress || 5}%` }}
                          />
                        </div>

                        {j.status === "completed" ? (
                          <div className="card-actions">
                            <a
                              className="download-btn primary full-width sm"
                              href={`${API}/api/jobs/${j.id}/download`}
                              target="_blank"
                              rel="noreferrer"
                              download={`video_product_${idx + 1}.mp4`}
                            >
                              📥 Tải Video #{idx + 1} (.mp4)
                            </a>
                          </div>
                        ) : j.status === "failed" ? (
                          <div className="item-error">❌ {j.error}</div>
                        ) : (
                          <div className="rendering-meta">⏱️ Đang ghép âm thanh & hiệu ứng...</div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            )}
          </div>
        )}

        {activeTab === "reup" && (
          <div className="tab-content">
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
                  <strong>
                    {apiSettings?.has_groq ? "⚡ Siêu tốc Groq Whisper" : "✓ Nhận diện Whisper"}
                  </strong>
                  <span>
                    {apiSettings?.has_groq
                      ? "Đang kích hoạt Groq Whisper Cloud: Xử lý âm thanh chỉ trong ~1 giây."
                      : "Nhận diện giọng nói chuẩn xác bằng Whisper AI (Bấm Cài Đặt API để tăng tốc 10x)."}
                  </span>
                </div>
                <div className="option">
                  <strong>
                    {apiSettings?.has_gemini ? "🚀 Dịch thuật Gemini Flash" : "✓ Dịch thuật thông minh"}
                  </strong>
                  <span>
                    {apiSettings?.has_gemini
                      ? "Đang dùng Google Gemini Flash: Phụ đề dịch tự nhiên, chuẩn ngữ cảnh lồng tiếng."
                      : "Tự động dịch sang tiếng Việt và cân bằng thời lượng khớp khẩu hình nhân vật."}
                  </span>
                </div>
                <div className="option">
                  <strong>✓ Lồng tiếng & Xuất SRT</strong>
                  <span>Đồng bộ chính xác từng mili-giây, giữ trọn âm thanh và nhạc nền gốc.</span>
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
          </div>
        )}

        {/* API Key Modal */}
        <ApiKeyModal
          isOpen={isApiModalOpen}
          onClose={() => setIsApiModalOpen(false)}
          apiBase={API}
          onSettingsSaved={(newSettings) => {
            setApiSettings(newSettings);
            loadVoices();
          }}
        />
      </main>
    </div>
  );
}

createRoot(document.getElementById("root")).render(<App />);
