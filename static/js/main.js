function togglePassword(inputId, button) {

    const passwordInput = document.getElementById(inputId);

    if (!passwordInput) {
        return;
    }

    const openEye = `
        <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
            aria-hidden="true"
        >
            <path d="M2.062 12.348a1 1 0 0 1 0-.696C3.424 7.51 7.36 5 12 5c4.639 0 8.573 2.51 9.938 6.652a1 1 0 0 1 0 .696C20.576 16.49 16.64 19 12 19c-4.639 0-8.573-2.51-9.938-6.652Z"/>
            <circle cx="12" cy="12" r="3"/>
        </svg>
    `;

    const closedEye = `
        <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
            aria-hidden="true"
        >
            <path d="m3 3 18 18"/>
            <path d="M10.584 10.587a2 2 0 0 0 2.828 2.828"/>
            <path d="M9.363 5.365A9.466 9.466 0 0 1 12 5c4.639 0 8.573 2.51 9.938 6.652a1 1 0 0 1 0 .696 10.97 10.97 0 0 1-1.682 2.887"/>
            <path d="M6.61 6.61C4.665 7.828 3.18 9.58 2.062 11.652a1 1 0 0 0 0 .696C3.424 16.49 7.36 19 12 19a9.83 9.83 0 0 0 5.39-1.61"/>
        </svg>
    `;

    if (passwordInput.type === "password") {

        passwordInput.type = "text";

        button.innerHTML = closedEye;

        button.setAttribute(
            "aria-label",
            "Hide password"
        );

    } else {

        passwordInput.type = "password";

        button.innerHTML = openEye;

        button.setAttribute(
            "aria-label",
            "Show password"
        );
    }
}