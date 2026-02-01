document.addEventListener("DOMContentLoaded", () => {
    // Select all audio elements on the page
    const audios = document.querySelectorAll("audio");

    audios.forEach(audio => {
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