document.addEventListener("DOMContentLoaded", () => {
const registerForm = document.getElementById("register-form");
if (!registerForm) return;

registerForm.addEventListener("submit", async (e) => {  
    e.preventDefault();  
    const res = await fetch("/register", {  
        method: "POST",  
        headers: { "Content-Type": "application/json" },  
        credentials: "same-origin",  
        body: JSON.stringify({  
            name: registerForm.name.value,  
            email: registerForm.email.value,  
            password: registerForm.password.value,  
            department: registerForm.department.value,  
            level: registerForm.level.value  
        })  
    });  
    const data = await res.json();  
    const msgEl = document.getElementById("register-msg");  
    if (res.ok) {  
        msgEl.style.color = "green";  
        msgEl.textContent = "Registration successful! Redirecting...";  
        setTimeout(() => window.location.href = data.redirect, 1500);  
    } else {  
        msgEl.style.color = "red";  
        msgEl.textContent = data.error;  
    }  
});

});
