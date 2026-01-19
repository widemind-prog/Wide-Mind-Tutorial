document.addEventListener("DOMContentLoaded", () => {
    // Select all audio elements on the page
    const audios = document.querySelectorAll("audio");

    audios.forEach(audio => {
        // Prevent right-click
        audio.addEventListener("contextmenu", e => e.preventDefault());

        // Prevent dragging
        audio.addEventListener("dragstart", e => e.preventDefault());

        // Ensure download button is hidden (modern browsers)
        audio.setAttribute("controlsList", "nodownload");
    });
});