# SubsOnVid

A powerful, local, and privacy-first web application for automatically generating, editing, and burning subtitles into your videos. Powered by OpenAI's Whisper model and FFmpeg, everything runs entirely on your own hardware.

## ✨ Features

*   **100% Local & Private:** No videos are uploaded to the cloud. All processing happens on your machine.
*   **AI Auto-Transcription:** Uses OpenAI's Whisper (choose between Tiny, Base, Small, Medium, Large, or Turbo models).
*   **Word-by-Word or N-Words:** Choose to display subtitles fully, line-by-line, word-by-word, or a custom number of words per screen.
*   **Hindi Transliteration:** Automatically transliterate Hindi audio into English/Roman script.
*   **Interactive Editor:** 
    *   Edit transcribed text directly in the browser.
    *   **Full Transcript Mode:** Copy the entire transcript, edit it externally (e.g., using ChatGPT for translation or grammar correction), and paste it back to automatically re-inject it while preserving timestamps.
*   **Custom Styling:** Fully customize font family, size, color, outline, and screen position.
*   **Sync offset control:** Easily fix audio/subtitle desync (Whisper delay) by shifting timestamps milliseconds forward or backward.
*   **Flexible Output:** Choose between **Hardcoded** (burned into the video pixels) or **Softcoded** (toggled on/off in media players).
*   **Mobile/WiFi Access:** Start the app on your PC and access the full editor from your iPhone or any other phone on the same WiFi network via a simple QR code scan. Iterate on edits without re-uploading!

## 🚀 Prerequisites

1.  **Python 3.8+** installed on your system.
2.  **FFmpeg** installed and added to your system's PATH.
    *   Windows: Download from gyan.dev or use `winget install ffmpeg`
    *   Mac: `brew install ffmpeg`
    *   Linux: `sudo apt install ffmpeg`

## 🛠️ Installation

1.  Clone this repository or download the source code.
2.  Navigate to the project directory in your terminal.
3.  Create a virtual environment (recommended):
    ```bash
    python -m venv venv
    venv\Scripts\activate  # On Windows
    # source venv/bin/activate  # On Mac/Linux
    ```
4.  Install the required dependencies:
    ```bash
    pip install -r requirements.txt
    ```
    *Note: When you run the app for the first time, Whisper will automatically download the necessary AI models.*

## 💻 Usage

1.  Start the application:
    ```bash
    python app.py
    ```
2.  Open your web browser and go to the local URL provided in the terminal (usually `http://127.0.0.1:5001`).
3.  **To use on your phone:** Look at the terminal output for the `On your phone` network URL, or simply click the 📱 button in the desktop web app and scan the QR code.
4.  **Workflow:**
    *   Upload your video.
    *   Select your processing options and transcribe.
    *   Edit the subtitles or adjust the words-per-screen.
    *   Style your subtitles (if hardcoding).
    *   Burn the video and download the final result!

## 📝 License

This project is open-source and available for personal use.
