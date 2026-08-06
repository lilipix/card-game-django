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

    const liveGameNode = document.querySelector(".js-live-game");
    if (!liveGameNode) {
        return;
    }

    const stateUrl = liveGameNode.dataset.stateUrl;
    const detailUrl = liveGameNode.dataset.detailUrl;
    const initialStatus = liveGameNode.dataset.status;
    const initialRound = Number.parseInt(liveGameNode.dataset.round || "0", 10);
    const initialStateNode = document.getElementById("live-game-state");

    if (!stateUrl || !detailUrl) {
        return;
    }

    const normalizeState = (value) => {
        if (value === null || typeof value !== "object") {
            return JSON.stringify(value);
        }
        if (Array.isArray(value)) {
            return `[${value.map((item) => normalizeState(item)).join(",")}]`;
        }
        const entries = Object.keys(value)
            .sort()
            .map((key) => `${JSON.stringify(key)}:${normalizeState(value[key])}`);
        return `{${entries.join(",")}}`;
    };

    const initialState = initialStateNode ? JSON.parse(initialStateNode.textContent || "{}") : null;
    let currentSnapshot = initialState ? normalizeState(initialState) : "";
    let currentStatus = initialStatus;
    let currentRound = Number.isNaN(initialRound) ? 0 : initialRound;
    let isPolling = false;
    let lastReloadAt = Date.now();

    const reloadGamePage = () => {
        lastReloadAt = Date.now();
        window.location.reload();
    };

    const pollGameState = async () => {
        if (isPolling) {
            return;
        }
        isPolling = true;
        try {
            const response = await fetch(stateUrl, {
                method: "GET",
                headers: { "X-Requested-With": "XMLHttpRequest" },
                credentials: "same-origin",
                cache: "no-store",
            });
            if (!response.ok) {
                return;
            }
            const gameState = await response.json();
            const nextSnapshot = normalizeState(gameState);
            const nextStatus = gameState.status;
            const nextRound = Number.isFinite(gameState.current_round)
                ? gameState.current_round
                : currentRound;

            if (nextSnapshot !== currentSnapshot || nextStatus !== currentStatus || nextRound !== currentRound) {
                reloadGamePage();
                return;
            }
        } catch (_error) {
            // Erreur réseau temporaire: on attend le prochain cycle.
        } finally {
            isPolling = false;
        }
    };

    window.setInterval(pollGameState, 1500);
    window.setInterval(() => {
        if (document.visibilityState !== "visible") {
            return;
        }
        if (Date.now() - lastReloadAt < 8000) {
            return;
        }
        reloadGamePage();
    }, 8000);

    window.addEventListener("focus", () => {
        reloadGamePage();
    });

    document.addEventListener("visibilitychange", () => {
        if (document.visibilityState === "visible") {
            reloadGamePage();
        }
    });
});
