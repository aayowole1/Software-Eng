"use strict";

window.orgflowGoogleSignIn = function (response) {
  const form = document.getElementById("google-signin-form");
  if (!form || !response || typeof response.credential !== "string" || !response.credential) {
    const error = document.getElementById("google-signin-error");
    if (error) {
      error.textContent = "Google sign-in did not complete. Please try again.";
      error.hidden = false;
    }
    return;
  }
  form.elements.namedItem("credential").value = response.credential;
  form.submit();
};
