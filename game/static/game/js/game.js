// Effets purement cosmétiques : aucune règle du jeu n'est décidée ici,
// le serveur reste seul responsable des cartes, du score et des manches.
document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll(".alert").forEach((alert) => {
        setTimeout(() => {
            alert.style.transition = "opacity 400ms ease";
            alert.style.opacity = "0";
        }, 4000);
    });

    document.querySelectorAll("form").forEach((form) => {
        form.addEventListener("submit", () => {
            const submitButton = form.querySelector("button[type='submit']");
            if (submitButton && !submitButton.disabled) {
                submitButton.disabled = true;
            }
        });
    });
});
