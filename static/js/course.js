document.addEventListener("DOMContentLoaded", async () => {
  // -------------------------
  // 1. Check payment status
  // -------------------------
  let hasAccess = false;
  try {
    const res = await fetch("api/payment/status");
    const data = await res.json();

    if (res.ok && data.status !== "unpaid") {
      hasAccess = true;
    }
  } catch (err) {
    console.error("Payment check failed:", err);
  }

  // -------------------------
  // 2. Handle audio elements
  // -------------------------
  const audios = document.querySelectorAll("audio");
  audios.forEach(audio => {
    // Prevent right-click and dragging
    audio.addEventListener("contextmenu", e => e.preventDefault());
    audio.addEventListener("dragstart", e => e.preventDefault());

    // Disable audio if user hasn't paid
    if (!hasAccess) {
      audio.pause();
      audio.controls = false;
      audio.parentElement.insertAdjacentHTML(
        "beforeend",
        `<p style="color:red; font-weight:bold;">🔒 Payment required to play this audio.</p>`
      );
    }
  });

  // -------------------------
  // 3. Handle PDF links
  // -------------------------
  const pdfLinks = document.querySelectorAll(".materials-box a.btn");
  pdfLinks.forEach(link => {
    if (!hasAccess) {
      link.addEventListener("click", e => {
        e.preventDefault();
        alert("Payment required to access this PDF.");
      });
      link.style.pointerEvents = "auto"; // just in case
      link.style.opacity = "0.5";
      link.style.textDecoration = "line-through";
    }
  });
});