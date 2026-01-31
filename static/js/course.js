document.addEventListener("DOMContentLoaded", () => {
    // Select all audio elements on the page
    const audios = document.querySelectorAll("audio");

    audios.forEach(audio => {
        // Prevent right-click on audio only
        audio.addEventListener("contextmenu", e => e.preventDefault());

        // Prevent dragging
        audio.addEventListener("dragstart", e => e.preventDefault());

        // Hide download option and prevent changing playback rate
        audio.setAttribute("controlsList", "nodownload noplaybackrate");

        // Disable Picture-in-Picture
        audio.setAttribute("disablePictureInPicture", "true");

        // Optional: force audio controls to be left-aligned
        audio.style.display = "block";
        audio.style.marginLeft = "0";
        audio.style.marginRight = "auto";
    });
});