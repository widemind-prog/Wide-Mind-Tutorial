document.addEventListener("DOMContentLoaded", async () => {
  // -------------------------
  // 1. Check payment status
  // -------------------------
  let hasAccess = false;
  try {
    const res = await fetch("/api/payment/status", { credentials: "same-origin" });
    const data = await res.json();
    if (res.ok && data.status === "paid") {
      hasAccess = true;
    }
  } catch (err) {
    console.error("Payment check failed:", err);
  }

  // -------------------------
  // 2. Populate course boxes
  // -------------------------
  const courseContainer = document.getElementById("course-list") || document.getElementById("courses");
  if (courseContainer) {
    try {
      const res = await fetch("/api/courses", { credentials: "same-origin" });
      if (!res.ok) {
        courseContainer.innerHTML = "<p style='color:red;'>Failed to load courses.</p>";
        return;
      }
      const data = await res.json();
      if (!data.length) {
        courseContainer.innerHTML = "<p>No courses available.</p>";
        return;
      }
      courseContainer.innerHTML = "";
      data.forEach(entry => {
        const course = entry.course;
        const materials = entry.materials;

        const courseDiv = document.createElement("div");
        courseDiv.className = "course-box";
        courseDiv.innerHTML = `
          <h3>${course.course_title} (${course.course_code})</h3>
          <p>${course.description || ""}</p>
          <ul>
            ${materials.map(m => {
              const url = `/stream/${m.file_type}/${m.id}`;
              const title = m.title || "Material";
              if (!hasAccess) {
                return `<li>${title} 🔒 Payment required</li>`;
              }
              return `<li><a href="${url}" target="_blank">${title}</a></li>`;
            }).join("")}
          </ul>
        `;
        courseContainer.appendChild(courseDiv);
      });
    } catch (err) {
      console.error("Failed to load courses:", err);
      if (courseContainer) {
        courseContainer.innerHTML = "<p style='color:red;'>Error loading courses</p>";
      }
    }
  }

  // -------------------------
  // 3. Handle audio elements (disable if unpaid)
  // -------------------------
  const audios = document.querySelectorAll("audio");
  audios.forEach(audio => {
    audio.addEventListener("contextmenu", e => e.preventDefault());
    audio.addEventListener("dragstart", e => e.preventDefault());
    if (!hasAccess) {
      audio.pause();
      audio.controls = false;
      if (!audio.nextElementSibling || !audio.nextElementSibling.classList.contains("locked-msg")) {
        const msg = document.createElement("p");
        msg.className = "locked-msg";
        msg.style.color = "red";
        msg.style.fontWeight = "bold";
        msg.textContent = "🔒 Payment required to play this audio.";
        audio.parentElement.appendChild(msg);
      }
    }
  });

  // -------------------------
  // 4. Handle PDF links (disable if unpaid)
  // -------------------------
  const pdfLinks = document.querySelectorAll("a.pdf-link");
  pdfLinks.forEach(link => {
    if (!hasAccess) {
      link.removeAttribute("href");
      link.style.color = "gray";
      link.textContent += " 🔒 Payment required";
    }
  });
});