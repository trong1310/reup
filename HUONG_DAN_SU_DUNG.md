# 📖 HƯỚNG DẪN SỬ DỤNG & CÁCH LẤY API KEY TĂNG TỐC VIDEO

Ứng dụng **AI Video Dubber** cho phép tải video (Douyin, TikTok, YouTube...), tự động nhận diện giọng nói, dịch thuật thông minh và lồng tiếng AI tiếng Việt chất lượng cao.

> [!NOTE]
> **TẤT CẢ API KEY ĐỀU LÀ TÙY CHỌN (CÓ THỂ ĐỂ TRỐNG / NULL)**  
> Nếu bạn không nhập bất kỳ API key nào, ứng dụng vẫn chạy **100% Offline / Miễn phí** bằng CPU của máy tính.  
> Tuy nhiên, khi nhập **Groq** và **Gemini** (đều miễn phí), video sẽ được xử lý **nhanh hơn gấp 10 lần** (nhận diện âm thanh chỉ mất ~1 giây).

---

## ⚡ 1. Hướng Dẫn Chi Tiết Cách Lấy API Key Từng Bên (Miễn Phí)

### 1️⃣ Groq Cloud API (`GROQ_API_KEY`) — *Siêu Tốc ~1 Giây • Miễn Phí*
- **Vai trò**: Tăng tốc nhận diện âm thanh Whisper từ ~1-2 phút (CPU) xuống còn **~1 giây**, dịch thuật siêu tốc Llama 3.3.
- **Chi phí**: **Miễn phí 100%** (Gói Free cực kỳ hào phóng).
- **Cách lấy**:
  1. Truy cập: [https://console.groq.com/keys](https://console.groq.com/keys)
  2. Đăng nhập bằng tài khoản Google hoặc GitHub.
  3. Bấm vào nút **`Create API Key`**.
  4. Đặt tên bất kỳ (ví dụ: `VideoDubber`) rồi bấm **Submit**.
  5. Copy mã Key bắt đầu bằng chữ `gsk_...` và dán vào Popup của ứng dụng.

---

### 2️⃣ Google Gemini API (`GEMINI_API_KEY`) — *Dịch Phụ Đề Chuẩn Nhất • Miễn Phí*
- **Vai trò**: Dịch toàn bộ phụ đề video trong 1 lần duy nhất (~1 giây). Câu từ tự nhiên, chuẩn ngữ cảnh lồng tiếng.
- **Chi phí**: **Miễn phí 100%** (Hỗ trợ model `Gemini 1.5/2.0 Flash`).
- **Cách lấy**:
  1. Truy cập: [https://aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey)
  2. Đăng nhập bằng tài khoản Google của bạn.
  3. Bấm nút **`Create API key`** (hoặc `Get API key`).
  4. Chọn một Project mặc định hoặc tạo mới rồi bấm **Create**.
  5. Copy mã Key bắt đầu bằng `AIzaSy...` và dán vào Popup của ứng dụng.

---

### 3️⃣ OpenAI API (`OPENAI_API_KEY`) — *Whisper-1 • GPT-4o • Giọng Đọc OpenAI*
- **Vai trò**: Nhận diện Whisper Cloud, dịch thuật GPT-4o-mini và **mở khóa 6 giọng đọc AI OpenAI** (`Alloy`, `Nova`, `Shimmer`, `Echo`, `Onyx`, `Fable`).
- **Chi phí**: Trả phí theo lưu lượng (hoặc credit dùng thử của tài khoản mới).
- **Cách lấy**:
  1. Truy cập: [https://platform.openai.com/api-keys](https://platform.openai.com/api-keys)
  2. Đăng nhập tài khoản OpenAI.
  3. Bấm **`+ Create new secret key`**.
  4. Copy mã Key bắt đầu bằng `sk-proj-...` và dán vào Popup của ứng dụng.
  *(Nếu không có tài khoản OpenAI trả phí, bạn có thể **để trống / null** ô này).*

---

### 4️⃣ ElevenLabs API (`ELEVENLABS_API_KEY`) — *Giọng Đọc Siêu Thực Thế Giới*
- **Vai trò**: Mở khóa dàn giọng đọc AI siêu thực, giàu cảm xúc (Rachel, Adam, Bella, Antoni...).
- **Chi phí**: Có gói Free 10.000 ký tự/tháng.
- **Cách lấy**:
  1. Truy cập: [https://elevenlabs.io](https://elevenlabs.io)
  2. Đăng ký tài khoản và đăng nhập.
  3. Bấm vào biểu tượng Avatar ở góc dưới bên trái → Chọn **Profile + API key**.
  4. Bấm biểu tượng con mắt để copy **API Key**.
  *(Nếu không dùng ElevenLabs, bạn có thể **để trống / null** ô này).*

---

### 5️⃣ Hugging Face Token (`HF_TOKEN`) — *Tải Model Offline Nhanh*
- **Vai trò**: Tải các model AI offline (VieNeu-TTS, Whisper local) với tốc độ cao, không bị giới hạn băng thông.
- **Chi phí**: **Miễn phí 100%**.
- **Cách lấy**:
  1. Truy cập: [https://huggingface.co/settings/tokens](https://huggingface.co/settings/tokens)
  2. Đăng nhập / Đăng ký tài khoản Hugging Face.
  3. Bấm **`Create new token`** → Chọn loại **Read** → Bấm **Create**.
  4. Copy mã Token bắt đầu bằng `hf_...` và dán vào Popup của ứng dụng.

---

## 📋 Bảng Tóm Tắt & Vai Trò Các API Key

| API Key | Đảm Nhiệm Vai Trò | Có Thể `null`? | Chi Phí |
| :--- | :--- | :---: | :---: |
| **`GROQ_API_KEY`** | Nhận diện giọng nói siêu tốc **~1 giây** (Whisper LPU) | **CÓ (null)** | Miễn phí |
| **`GEMINI_API_KEY`** | Dịch thuật AI thông minh, tự nhiên theo ngữ cảnh video | **CÓ (null)** | Miễn phí |
| **`OPENAI_API_KEY`** | Nhận diện Whisper, dịch GPT-4o, mở khóa giọng OpenAI | **CÓ (null)** | Trả phí / Credit |
| **`ELEVENLABS_API_KEY`**| Mở khóa giọng đọc lồng tiếng siêu thực đa ngôn ngữ | **CÓ (null)** | Free 10k ký tự/tháng |
| **`HF_TOKEN`** | Tăng tốc tải model offline từ Hugging Face | **CÓ (null)** | Miễn phí |

---

## 🚀 2. Hướng Dẫn Cách Nhập Key & Sử Dụng Ứng Dụng

### Bước 1: Khởi động ứng dụng
- Nhấp đúp chuột vào file **`start-all.bat`** ở thư mục gốc của dự án.
- Ứng dụng sẽ tự động mở giao diện Desktop.

### Bước 2: Nhập API Key vào Popup
1. Trên giao diện ứng dụng, bấm vào nút **`⚡ Cấu Hình API Key (Tăng Tốc 10x)`** ở góc trên cùng.
2. Dán các mã Key bạn đã lấy vào ô tương ứng (khuyên dùng ít nhất 2 key miễn phí: **Groq** và **Gemini**).
3. Bấm nút **`⚡ Test Kết Nối`** bên cạnh mỗi key để kiểm tra kết nối với máy chủ (kết quả hiển thị độ trễ màu xanh `✅ Hợp lệ (120ms)`).
4. Bấm **`💾 Lưu & Áp Dụng Ngay`**.

### Bước 3: Xử lý video lồng tiếng
1. **Dán link video**: Dán đường dẫn video từ Douyin, TikTok, YouTube hoặc video ngắn.
2. **Chọn ngôn ngữ**:
   - Ngôn ngữ nguồn: *Tự động nhận diện (Auto)* hoặc chọn tiếng Trung, tiếng Anh...
   - Ngôn ngữ đích: *Tiếng Việt (Vietnamese)*.
3. **Chọn giọng đọc AI**:
   - Giọng VieNeu AI Offline: *🌟 Ngọc Huyền v2*, *🌸 Ngọc Lan*, *🎙️ Gia Bảo*, *⚡ Thái Sơn*...
   - Giọng Edge-TTS: *Hoài My (Nữ)*, *Nam Minh (Nam)*...
   - Giọng OpenAI Cloud (khi có key): *Alloy*, *Nova*, *Shimmer*, *Echo*, *Onyx*, *Fable*...
4. Bấm **`🚀 BẮT ĐẦU XỬ LÝ`**.
5. Sau khi thanh tiến trình hoàn tất 100%, bấm **`🎬 Tải Video Hoàn Thành (.mp4)`** hoặc **`📝 Tải Tệp Phụ Đề (.srt)`**.
