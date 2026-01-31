const thumb = document.getElementById("scroll-thumb");
const track = document.getElementById("scroll-track");
const btnTop = document.getElementById("scroll-top");
const btnBottom = document.getElementById("scroll-bottom");
const nav = document.getElementById("page-scroll-nav");

let hideTimeout;

function updateThumb() {
  const scrollHeight = document.documentElement.scrollHeight - window.innerHeight;
  const scrollTop = window.scrollY;
  const trackHeight = track.clientHeight;
  const thumbHeight = thumb.clientHeight;

  const top = (scrollTop / scrollHeight) * (trackHeight - thumbHeight);
  thumb.style.top = `${top}px`;
}

/* Show nav when scrolling */
function showNav() {
  nav.classList.add("show");
  clearTimeout(hideTimeout);
  hideTimeout = setTimeout(() => nav.classList.remove("show"), 2000); // hide after 2s idle
}

/* Scroll events */
window.addEventListener("scroll", () => {
  updateThumb();
  showNav();
});
window.addEventListener("resize", updateThumb);

/* Button clicks */
btnTop.onclick = () => window.scrollTo({ top: 0, behavior: "smooth" });
btnBottom.onclick = () =>
  window.scrollTo({ top: document.documentElement.scrollHeight, behavior: "smooth" });

/* Dragging logic */
let dragging = false;

thumb.addEventListener("mousedown", () => {
  dragging = true;
  document.body.style.userSelect = "none";
});

document.addEventListener("mouseup", () => {
  dragging = false;
  document.body.style.userSelect = "";
});

document.addEventListener("mousemove", e => {
  if (!dragging) return;

  const rect = track.getBoundingClientRect();
  let y = e.clientY - rect.top;
  y = Math.max(0, Math.min(y, rect.height - thumb.clientHeight));

  const percent = y / (rect.height - thumb.clientHeight);
  const scrollHeight = document.documentElement.scrollHeight - window.innerHeight;

  window.scrollTo(0, percent * scrollHeight);
});

/* Initialize */
updateThumb();