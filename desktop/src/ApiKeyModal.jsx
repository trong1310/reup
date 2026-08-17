import React, { useState, useEffect } from "react";

export default function ApiKeyModal({ isOpen, onClose, apiBase, onSettingsSaved }) {
  const [settings, setSettings] = useState({
    groq_api_key: "",
    gemini_api_key: "",
    openai_api_key: "",
    elevenlabs_api_key: "",
    deepgram_api_key: "",
    hf_token: "",
    stt_provider: "auto",
    translate_provider: "auto",
  });

  const [initialSettings, setInitialSettings] = useState({});
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [showPassword, setShowPassword] = useState({});
  const [testResults, setTestResults] = useState({});
  const [testingProvider, setTestingProvider] = useState({});
  const [toastMsg, setToastMsg] = useState("");

  // Load settings when modal opens
  useEffect(() => {
    if (isOpen) {
      fetchSettings();
    }
  }, [isOpen]);

  const fetchSettings = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${apiBase}/api/settings`);
      if (res.ok) {
        const data = await res.json();
        setSettings(data);
        setInitialSettings(data);
      }
    } catch (e) {
      console.error("Failed to load settings:", e);
    } finally {
      setLoading(false);
    }
  };

  const toggleShow = (provider) => {
    setShowPassword(prev => ({ ...prev, [provider]: !prev[provider] }));
  };

  const handleInputChange = (field, value) => {
    setSettings(prev => ({ ...prev, [field]: value }));
    // Reset test result if user changes key
    if (testResults[field.replace("_api_key", "").replace("_token", "")]) {
      setTestResults(prev => {
        const next = { ...prev };
        delete next[field.replace("_api_key", "").replace("_token", "")];
        return next;
      });
    }
  };

  const handleTestKey = async (provider, keyField) => {
    const rawVal = settings[keyField];
    setTestingProvider(prev => ({ ...prev, [provider]: true }));
    setTestResults(prev => ({ ...prev, [provider]: null }));

    try {
      const res = await fetch(`${apiBase}/api/settings/test`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider: provider,
          api_key: rawVal || null,
        }),
      });
      const data = await res.json();
      setTestResults(prev => ({ ...prev, [provider]: data }));
    } catch (e) {
      setTestResults(prev => ({
        ...prev,
        [provider]: { ok: false, error: "Lỗi kết nối tới máy chủ engine" },
      }));
    } finally {
      setTestingProvider(prev => ({ ...prev, [provider]: false }));
    }
  };

  const handleSave = async () => {
    setSaving(true);
    setToastMsg("");
    try {
      const payload = { ...settings };
      const res = await fetch(`${apiBase}/api/settings`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (res.ok) {
        const data = await res.json();
        setSettings(data.settings);
        setInitialSettings(data.settings);
        setToastMsg("✅ Đã lưu và kích hoạt cấu hình API thành công!");
        if (onSettingsSaved) onSettingsSaved(data.settings);
        setTimeout(() => setToastMsg(""), 3500);
      } else {
        setToastMsg("❌ Lỗi khi lưu cấu hình.");
      }
    } catch (e) {
      setToastMsg("❌ Không thể kết nối tới engine: " + e.message);
    } finally {
      setSaving(false);
    }
  };

  const handleClearKey = (field) => {
    setSettings(prev => ({ ...prev, [field]: "__CLEAR__" }));
  };

  if (!isOpen) return null;

  const providers = [
    {
      id: "groq",
      name: "⚡ Groq Cloud API",
      tag: "Siêu Tốc 1s • Khuyên Dùng",
      tagColor: "#10b981",
      desc: "Tăng tốc nhận diện giọng nói Whisper Cloud từ 1 phút xuống 1-2 giây và dịch thuật siêu tốc Llama 3.3.",
      field: "groq_api_key",
      hasKey: settings.has_groq,
      keyUrl: "https://console.groq.com/keys",
      placeholder: "gsk_...",
    },
    {
      id: "gemini",
      name: "🚀 Google Gemini API",
      tag: "Dịch Phụ Đề Chuẩn Xác Nhất",
      tagColor: "#38bdf8",
      desc: "Dịch thuật thông minh theo ngữ cảnh video bằng Gemini 1.5/2.0 Flash, câu từ tự nhiên chuẩn lồng tiếng.",
      field: "gemini_api_key",
      hasKey: settings.has_gemini,
      keyUrl: "https://aistudio.google.com/app/apikey",
      placeholder: "AIzaSy...",
    },
    {
      id: "openai",
      name: "🤖 OpenAI API",
      tag: "Whisper-1 • GPT-4o • Giọng Đọc OpenAI",
      tagColor: "#a855f7",
      desc: "Nhận diện giọng nói chuẩn xác, dịch thuật AI và mở khóa 6 giọng đọc lồng tiếng OpenAI Neural Cloud.",
      field: "openai_api_key",
      hasKey: settings.has_openai,
      keyUrl: "https://platform.openai.com/api-keys",
      placeholder: "sk-proj-...",
    },
    {
      id: "elevenlabs",
      name: "🎙️ ElevenLabs API",
      tag: "Giọng Đọc Siêu Thực",
      tagColor: "#f59e0b",
      desc: "Mở khóa dàn giọng đọc AI siêu thực, biểu cảm tự nhiên hàng đầu thế giới (Rachel, Adam, Bella...).",
      field: "elevenlabs_api_key",
      hasKey: settings.has_elevenlabs,
      keyUrl: "https://elevenlabs.io",
      placeholder: "xi-api-key...",
    },
    {
      id: "huggingface",
      name: "🤗 Hugging Face Token",
      tag: "Tải Model Offline Nhanh",
      tagColor: "#ec4899",
      desc: "Tải các model VieNeu AI và Whisper Offline tốc độ cao không bị giới hạn lưu lượng.",
      field: "hf_token",
      hasKey: settings.has_hf,
      keyUrl: "https://huggingface.co/settings/tokens",
      placeholder: "hf_...",
    },
  ];

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-content" onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="modal-header">
          <div className="modal-title-group">
            <div className="modal-icon-badge">⚡</div>
            <div>
              <h2>Cấu Hình API Key & Tăng Tốc Xử Lý Video</h2>
              <p>Tích hợp các nhà cung cấp AI đám mây để xử lý video nhanh gấp 10 lần và nâng cao chất lượng dịch/giọng đọc.</p>
            </div>
          </div>
          <button className="modal-close-btn" onClick={onClose} title="Đóng">✕</button>
        </div>

        {toastMsg && (
          <div className={`modal-toast ${toastMsg.startsWith("✅") ? "success" : "error"}`}>
            {toastMsg}
          </div>
        )}

        {loading ? (
          <div className="modal-loading">
            <div className="spinner" />
            <span>Đang tải cấu hình hiện tại...</span>
          </div>
        ) : (
          <div className="modal-body">
            {/* Routing Preferences */}
            <div className="preference-section">
              <h3 className="section-title">🛠️ Lựa Chọn Bộ Tăng Tốc Ưu Tiên</h3>
              <div className="pref-grid">
                <div className="pref-box">
                  <label>Nhận diện âm thanh (Speech-to-Text):</label>
                  <select
                    value={settings.stt_provider || "auto"}
                    onChange={e => handleInputChange("stt_provider", e.target.value)}
                  >
                    <option value="auto">⚡ Tự động (Ưu tiên Groq 1s → OpenAI → Local)</option>
                    <option value="groq">⚡ Groq Whisper Cloud (Siêu Tốc ~1s - Khuyên Dùng)</option>
                    <option value="openai">🤖 OpenAI Whisper Cloud</option>
                    <option value="local">💻 Local Faster-Whisper (CPU máy tính)</option>
                  </select>
                </div>

                <div className="pref-box">
                  <label>Dịch thuật phụ đề (Translation AI):</label>
                  <select
                    value={settings.translate_provider || "auto"}
                    onChange={e => handleInputChange("translate_provider", e.target.value)}
                  >
                    <option value="auto">🚀 Tự động (Ưu tiên Gemini Flash → Groq → Google)</option>
                    <option value="gemini">🚀 Google Gemini Flash (Tự nhiên & Ngữ cảnh chuẩn)</option>
                    <option value="groq">⚡ Groq Llama 3.3 70B (Siêu tốc dưới 1 giây)</option>
                    <option value="openai">🤖 OpenAI GPT-4o-mini</option>
                    <option value="google">🌐 Google Dịch Thường (Miễn phí)</option>
                  </select>
                </div>
              </div>
            </div>

            {/* Providers List */}
            <div className="providers-list">
              <h3 className="section-title">🔑 Danh Sách API Key Bên Thứ 3</h3>
              
              {providers.map(p => {
                const isTesting = testingProvider[p.id];
                const result = testResults[p.id];
                const isPasswordShown = showPassword[p.id];
                const currentValue = settings[p.field] || "";
                const isCleared = currentValue === "__CLEAR__";
                const isConfigured = p.hasKey && !isCleared;

                return (
                  <div className={`provider-card ${isConfigured ? "configured" : ""}`} key={p.id}>
                    <div className="provider-header">
                      <div className="provider-info">
                        <h4>{p.name}</h4>
                        <span className="provider-tag" style={{ borderColor: p.tagColor, color: p.tagColor, background: `${p.tagColor}15` }}>
                          {p.tag}
                        </span>
                        {isConfigured && (
                          <span className="active-badge">✓ Đã Kết Nối</span>
                        )}
                        {isCleared && (
                          <span className="cleared-badge">✕ Sẽ Bị Xóa</span>
                        )}
                      </div>
                      <a
                        href={p.keyUrl}
                        target="_blank"
                        rel="noreferrer"
                        className="get-key-link"
                      >
                        Lấy API Key Miễn Phí ↗
                      </a>
                    </div>

                    <p className="provider-desc">{p.desc}</p>

                    <div className="key-input-row">
                      <div className="input-wrap">
                        <input
                          type={isPasswordShown ? "text" : "password"}
                          value={isCleared ? "" : currentValue}
                          placeholder={isConfigured ? "(Đã lưu bảo mật - Nhập mã mới nếu muốn đổi)" : p.placeholder}
                          onChange={e => handleInputChange(p.field, e.target.value)}
                        />
                        <button
                          type="button"
                          className="toggle-eye-btn"
                          onClick={() => toggleShow(p.id)}
                          title={isPasswordShown ? "Ẩn" : "Hiện"}
                        >
                          {isPasswordShown ? "👁️" : "🙈"}
                        </button>
                      </div>

                      <button
                        type="button"
                        className={`test-btn ${isTesting ? "testing" : ""}`}
                        onClick={() => handleTestKey(p.id, p.field)}
                        disabled={isTesting || (!currentValue && !p.hasKey)}
                      >
                        {isTesting ? (
                          <>
                            <div className="mini-spinner" />
                            <span>Đang test...</span>
                          </>
                        ) : (
                          <span>⚡ Test Kết Nối</span>
                        )}
                      </button>

                      {isConfigured && !isCleared && (
                        <button
                          type="button"
                          className="clear-btn"
                          onClick={() => handleClearKey(p.field)}
                          title="Xóa Key này"
                        >
                          Xóa
                        </button>
                      )}
                    </div>

                    {/* Test result status */}
                    {result && (
                      <div className={`test-feedback ${result.ok ? "success" : "error"}`}>
                        {result.ok ? (
                          <>
                            <span className="feedback-icon">✓</span>
                            <span>{result.message || "Kết nối thành công!"}</span>
                            {result.latency_ms && (
                              <span className="latency-badge">{result.latency_ms}ms</span>
                            )}
                          </>
                        ) : (
                          <>
                            <span className="feedback-icon">⚠️</span>
                            <span>{result.error || "Lỗi kiểm tra API Key"}</span>
                          </>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Footer */}
        <div className="modal-footer">
          <button className="cancel-btn" onClick={onClose}>
            Đóng
          </button>
          <button
            className={`save-btn ${saving ? "loading" : ""}`}
            onClick={handleSave}
            disabled={saving || loading}
          >
            {saving ? (
              <>
                <div className="spinner" />
                <span>Đang lưu...</span>
              </>
            ) : (
              <span>💾 Lưu & Áp Dụng Ngay</span>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
