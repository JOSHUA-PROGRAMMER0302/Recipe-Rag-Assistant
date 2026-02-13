(function () {
  function fromQueryParam() {
    try {
      const params = new URLSearchParams(window.location.search);
      const api = params.get('api');
      return api && api.trim() ? api.trim() : null;
    } catch {
      return null;
    }
  }

  function isLocalhost(hostname) {
    return hostname === 'localhost' || hostname === '127.0.0.1' || hostname === '0.0.0.0';
  }

  function computeDefaultApiBase() {
    if (isLocalhost(window.location.hostname)) {
      return 'http://localhost:8000';
    }
    // Default Render URL (change if you use a different service name)
    return 'https://recipe-rag-assistant-api.onrender.com';
  }

  // Priority: explicit global -> ?api= -> environment-based default
  window.API_BASE = window.API_BASE || fromQueryParam() || computeDefaultApiBase();
})();
