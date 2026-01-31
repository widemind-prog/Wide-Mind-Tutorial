document.addEventListener("DOMContentLoaded", () => {
    const audios = document.querySelectorAll("audio");

    audios.forEach(audio => {
        // Prevent right-click on audio only
        audio.addEventListener("contextmenu", e => e.preventDefault());

        // Prevent dragging
        audio.addEventListener("dragstart", e => e.preventDefault());

        // Hide download option (where supported)
        audio.setAttribute("controlsList", "nodownload noplaybackrate");

        // Extra hardening
        audio.setAttribute("disablePictureInPicture", "true");
    });
});