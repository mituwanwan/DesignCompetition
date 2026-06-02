/**
 * 统一 Toast 通知工具
 * 所有页面共享，避免重复定义 showToast
 */

function showToast(message, type) {
    const container = document.getElementById('toastContainer') || (() => {
        const c = document.createElement('div');
        c.id = 'toastContainer';
        c.className = 'toast-container position-fixed top-0 end-0 p-3';
        document.body.appendChild(c);
        return c;
    })();
    const toast = document.createElement('div');
    toast.className = `toast align-items-center text-white bg-${type} border-0`;
    toast.innerHTML = `<div class="d-flex"><div class="toast-body">${message}</div>
        <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button></div>`;
    container.appendChild(toast);
    new bootstrap.Toast(toast).show();
    toast.addEventListener('hidden.bs.toast', () => toast.remove());
}
