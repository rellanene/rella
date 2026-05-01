// static/rella.js
document.addEventListener('DOMContentLoaded', function(){
  const container = document.getElementById('toast-container');

  function showToast(message, category='info', timeout=5000){
    const t = document.createElement('div');
    t.className = 'toast ' + (category || 'info');
    t.innerText = message;
    container.appendChild(t);
    // ensure toasts don't overlap content: container is bottom-left and main has bottom padding
    setTimeout(()=> {
      t.style.opacity = '0';
      t.style.transform = 'translateX(-10px)';
      setTimeout(()=> t.remove(), 400);
    }, timeout);
  }

  // show server-side flashed messages
  if (window.__RELLA_TOASTS && Array.isArray(window.__RELLA_TOASTS)){
    window.__RELLA_TOASTS.forEach(function(item, idx){
      showToast(item.message, item.category === 'error' ? 'error' : (item.category === 'success' ? 'success' : 'info'), 5000 + idx*300);
    });
    window.__RELLA_TOASTS = [];
  }

  // expose for other scripts
  window.RELLA = {
    toast: showToast
  };
});
