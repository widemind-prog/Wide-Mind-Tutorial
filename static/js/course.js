document.addEventListener("DOMContentLoaded", () => {
    // Select all audio elements on the page
    const audios = document.querySelectorAll("audio");

    audios.forEach(audio => {
        const audioId = audio.getAttribute("id") || audio.src; // unique key for localStorage

        // Load saved playback position
        const savedTime = localStorage.getItem(`audioTime_${audioId}`);
        if (savedTime) {
            audio.currentTime = parseFloat(savedTime);
        }

        // Save playback position every second
        audio.addEventListener("timeupdate", () => {
            localStorage.setItem(`audioTime_${audioId}`, audio.currentTime);
        });

        // Optional: Remove saved time when audio ends
        audio.addEventListener("ended", () => {
            localStorage.removeItem(`audioTime_${audioId}`);
        });

        // Prevent right-click on audio
        audio.addEventListener("contextmenu", e => e.preventDefault());

        // Prevent dragging the audio element
        audio.addEventListener("dragstart", e => e.preventDefault());

        // Hide download option
        audio.setAttribute("controlsList", "nodownload");

        // Disable Picture-in-Picture mode
        audio.setAttribute("disablePictureInPicture", "true");

        // Force left-aligned audio controls
        audio.style.display = "block";
        audio.style.marginLeft = "0";
        audio.style.marginRight = "auto";

        // Optional: Add a subtle tooltip to inform users
        audio.title = "Right-click and download disabled";
    });
});