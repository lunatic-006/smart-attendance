# Smart Face Recognition Attendance System

A modern, serverless web application that automates student attendance tracking using **client-side face recognition** and a **cloud-native database**. 

Built with Vanilla JavaScript, tailored for high performance straight in the browser without massive backend machine learning requirements.

---

## 🌟 Key Features

### For Students
- **Smart Registration**: Securely register using your ID and capture your face profile directly from your webcam.
- **Frictionless Verification**: Mark attendance instantly by just looking at the camera.
- **Client-Side Processing**: Facial recognition is completely handled in your browser. Images are never uploaded to a server—only mathematical descriptors are saved.

### For Lecturers
- **Class Session Management**: Create, view, and delete dynamic class sessions.
- **Real-Time Attendance Monitoring**: See exactly who is present, absent, or has "suspicious" attendance behavior (e.g. absent most of the class but registered a ping).
- **Automated Reporting**: Calculate attendance percentages automatically based on expected class duration.

---

## 🛠 Tech Stack

- **Frontend:** Vanilla HTML, CSS, JavaScript (Zero Build Steps)
- **Face Recognition:** [face-api.js](https://github.com/vladmandic/face-api) (TensorFlow.js wrapper for browser-based face detection)
- **Backend / Database:** [Appwrite Cloud](https://appwrite.io/) (Serverless Authentication & Document Database)
- **Hosting:** [Vercel](https://vercel.com/) (Static Edge Deployment)

---

## 🚀 Live Demo

**Deployed Application:** [https://smartattendancesystem-six.vercel.app](https://smartattendancesystem-six.vercel.app)

*(Note: Requires enabling Camera access in your browser)*

---

## ⚙️ Local Setup and Development

Since the ML models run client-side and everything speaks directly to the Appwrite Cloud APIs, local development is incredibly simple.

1. **Clone the repository:**
   ```bash
   git clone https://github.com/lunatic-006/smart-attendance.git
   cd smart-attendance
   ```

2. **Serve the files:**
   Since this is a vanilla HTML/JS app, you can use any basic web server to serve the root directory.
   ```bash
   # Using Python 3
   python -m http.server 8000
   
   # Or using Node.js (http-server)
   npx http-server ./frontend
   ```

3. **Open your browser:**
   Navigate to `http://localhost:8000/frontend/index.html`

---

## 🗄️ Database Schema & Appwrite Setup

The application connects to **Appwrite Cloud**. If you intend to run your own backend instance, you must configure an Appwrite project with the following 4 collections:

1. **Lecturers** (`name`, `lecturer_id`, `email`, `auth_user_id`)
2. **Students** (`name`, `roll_number`, `email`, `auth_user_id`, `face_encoding` [length: 1000000], `is_registered`)
3. **Class Sessions** (`lecturer_id`, `lecturer_custom_id`, `class_id`, `class_name`, `date`, `start_time`, `end_time`, `total_expected_pings`)
4. **Attendance Records** (`session_id`, `student_id`, `ping_count`, `first_seen_time`)

*A setup script (`setup-appwrite.mjs`) is provided in the repository to automatically scaffold these collections in your Appwrite instance.*

---

## 🔒 Security & Privacy

*   **PWA Compatibility**: Does not rely on backend APIs for heavy lifting.
*   **Privacy-first ML**: Raw webcam frames never leave the user's computer. The TensorFlow model extracts a 128-dimensional mathematical array locally. 
*   **Role-based UI**: Isolated login pipelines and dashboard environments for Students vs. Lecturers.

---

## 📜 License
This project is open-source and free to modify.
