document.addEventListener("DOMContentLoaded", () => {
  const audio = document.getElementById("audioPlayer");
  if (audio) {
    audio.addEventListener("contextmenu", e => e.preventDefault());
  }
});
