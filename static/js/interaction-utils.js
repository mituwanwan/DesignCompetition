window.InteractionUtils = (function() {

    function initRippleEffect() {
        document.addEventListener('click', function(e) {
            var btn = e.target.closest('.btn');
            if (!btn) return;

            var rect = btn.getBoundingClientRect();
            var x = e.clientX - rect.left;
            var y = e.clientY - rect.top;

            var ripple = document.createElement('span');
            ripple.className = 'ripple';
            ripple.style.left = x + 'px';
            ripple.style.top = y + 'px';

            var size = Math.max(rect.width, rect.height);
            ripple.style.width = ripple.style.height = size + 'px';
            ripple.style.marginLeft = -size / 2 + 'px';
            ripple.style.marginTop = -size / 2 + 'px';

            btn.style.position = 'relative';
            btn.style.overflow = 'hidden';
            btn.appendChild(ripple);

            ripple.addEventListener('animationend', function() {
                ripple.remove();
            });
        });
    }

    function initModalEnhancements() {
        document.addEventListener('shown.bs.modal', function(e) {
            var modal = e.target;
            var backdrop = document.querySelector('.modal-backdrop');
            if (backdrop) {
                backdrop.addEventListener('click', function() {
                    var bsModal = bootstrap.Modal.getInstance(modal);
                    if (bsModal) {
                        if (modal.dataset.confirmClose === 'true') {
                            handleUnsavedClose(modal, bsModal);
                        } else {
                            bsModal.hide();
                        }
                    }
                });
            }
        });

        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape') {
                var openModal = document.querySelector('.modal.show');
                if (openModal) {
                    var bsModal = bootstrap.Modal.getInstance(openModal);
                    if (bsModal) {
                        if (openModal.dataset.confirmClose === 'true') {
                            e.preventDefault();
                            e.stopPropagation();
                            handleUnsavedClose(openModal, bsModal);
                        }
                    }
                }
            }
        });
    }

    function handleUnsavedClose(modal, bsModal) {
        var form = modal.querySelector('form');
        if (!form) {
            bsModal.hide();
            return;
        }

        if (isFormDirty(form)) {
            if (confirm('您有未保存的数据，确定要关闭吗？')) {
                resetDirtyState(form);
                bsModal.hide();
            }
        } else {
            bsModal.hide();
        }
    }

    function isFormDirty(form) {
        if (form.dataset.dirty === 'true') return true;

        var inputs = form.querySelectorAll('input, select, textarea');
        for (var i = 0; i < inputs.length; i++) {
            var input = inputs[i];
            if (input.type === 'hidden') continue;
            if (input.type === 'button' || input.type === 'submit' || input.type === 'reset') continue;

            var defaultValue = input.getAttribute('data-default-value') || '';
            var currentValue = input.value;

            if (input.type === 'checkbox') {
                var defaultChecked = input.getAttribute('data-default-checked') === 'true';
                if (input.checked !== defaultChecked) return true;
            } else if (currentValue !== defaultValue) {
                return true;
            }
        }
        return false;
    }

    function markFormDirty(form) {
        form.dataset.dirty = 'true';
        var modal = form.closest('.modal');
        if (modal) {
            modal.dataset.confirmClose = 'true';
        }
        showUnsavedWarning();
    }

    function resetDirtyState(form) {
        form.dataset.dirty = 'false';
        var modal = form.closest('.modal');
        if (modal) {
            modal.dataset.confirmClose = 'false';
        }
        hideUnsavedWarning();
    }

    function initFormDirtyTracking() {
        document.addEventListener('input', function(e) {
            var input = e.target;
            var form = input.closest('form');
            if (!form) return;

            if (!form.dataset.trackingInitialized) {
                return;
            }

            markFormDirty(form);
        });

        document.addEventListener('change', function(e) {
            var input = e.target;
            var form = input.closest('form');
            if (!form || !form.dataset.trackingInitialized) return;

            markFormDirty(form);
        });
    }

    function trackForm(formSelector) {
        var form = document.querySelector(formSelector);
        if (!form) return;

        form.dataset.trackingInitialized = 'true';
        form.dataset.dirty = 'false';

        var inputs = form.querySelectorAll('input, select, textarea');
        inputs.forEach(function(input) {
            if (input.type === 'hidden') return;
            if (input.type === 'button' || input.type === 'submit' || input.type === 'reset') return;

            input.setAttribute('data-default-value', input.value);
            if (input.type === 'checkbox') {
                input.setAttribute('data-default-checked', input.checked.toString());
            }
        });
    }

    function showUnsavedWarning() {
        var warning = document.querySelector('.unsaved-changes-warning');
        if (!warning) return;
        warning.classList.add('show');
    }

    function hideUnsavedWarning() {
        var warning = document.querySelector('.unsaved-changes-warning');
        if (!warning) return;

        var dirtyForms = document.querySelectorAll('form[data-dirty="true"]');
        if (dirtyForms.length === 0) {
            warning.classList.remove('show');
        }
    }

    var shortcuts = {};
    var shortcutDescriptions = {};

    function registerShortcut(key, ctrlKey, altKey, shiftKey, callback, description) {
        var combo = buildCombo(key, ctrlKey, altKey, shiftKey);
        shortcuts[combo] = callback;
        shortcutDescriptions[combo] = description || combo;
    }

    function buildCombo(key, ctrlKey, altKey, shiftKey) {
        var parts = [];
        if (ctrlKey) parts.push('Ctrl');
        if (altKey) parts.push('Alt');
        if (shiftKey) parts.push('Shift');
        parts.push(key.toUpperCase());
        return parts.join('+');
    }

    function initKeyboardShortcuts() {
        document.addEventListener('keydown', function(e) {
            var target = e.target;
            var isInput = target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.tagName === 'SELECT';

            if (e.key === 'Escape') return;

            var combo = buildCombo(e.key, e.ctrlKey, e.altKey, e.shiftKey);

            if (shortcuts[combo]) {
                if (isInput && !e.ctrlKey && !e.altKey) return;
                e.preventDefault();
                shortcuts[combo]();
            }
        });
    }

    function getShortcutDescriptions() {
        return Object.keys(shortcutDescriptions).map(function(combo) {
            return { combo: combo, description: shortcutDescriptions[combo] };
        });
    }

    function initDefaultShortcuts() {
        var role = document.querySelector('meta[name="user-role"]')?.content || '';

        registerShortcut('h', true, false, false, function() {
            if (role === 'admin') window.location.href = '/admin';
            else if (role === 'caregiver') window.location.href = '/caregiver';
            else if (role === 'family') window.location.href = '/family';
        }, '返回首页');

        registerShortcut('k', true, false, false, function() {
            var searchInput = document.querySelector('input[type="search"], input[placeholder*="搜索"], input[placeholder*="查找"]');
            if (searchInput) searchInput.focus();
        }, '聚焦搜索框');

        registerShortcut('n', true, false, false, function() {
            if (role === 'admin') window.location.href = '/admin/messages';
            else if (role === 'caregiver') window.location.href = '/caregiver/messages';
            else if (role === 'family') window.location.href = '/family/messages';
        }, '打开消息');

        registerShortcut('/', false, false, true, function() {
            showShortcutHelp();
        }, '显示快捷键帮助');

        registerShortcut('?', true, false, false, function() {
            showShortcutHelp();
        }, '显示快捷键帮助');
    }

    function showShortcutHelp() {
        var existingModal = document.getElementById('shortcutHelpModal');
        if (existingModal) {
            var bsModal = bootstrap.Modal.getInstance(existingModal);
            if (bsModal) {
                bsModal.show();
                return;
            }
        }

        var descriptions = getShortcutDescriptions();
        var listHtml = '';
        descriptions.forEach(function(item) {
            var keys = item.combo.split('+');
            var kbdHtml = keys.map(function(k) { return '<kbd>' + k + '</kbd>'; }).join(' + ');
            listHtml += '<li><span class="shortcut-desc">' + item.description + '</span><span>' + kbdHtml + '</span></li>';
        });

        var modalHtml = '<div class="modal fade" id="shortcutHelpModal" tabindex="-1">' +
            '<div class="modal-dialog modal-dialog-centered">' +
                '<div class="modal-content">' +
                    '<div class="modal-header">' +
                        '<h5 class="modal-title"><i class="bi bi-keyboard me-2"></i>键盘快捷键</h5>' +
                        '<button type="button" class="btn-close" data-bs-dismiss="modal"></button>' +
                    '</div>' +
                    '<div class="modal-body">' +
                        '<ul class="shortcut-list">' + listHtml + '</ul>' +
                    '</div>' +
                    '<div class="modal-footer">' +
                        '<button type="button" class="btn btn-secondary btn-sm" data-bs-dismiss="modal">关闭</button>' +
                    '</div>' +
                '</div>' +
            '</div>' +
        '</div>';

        document.body.insertAdjacentHTML('beforeend', modalHtml);
        var modalEl = document.getElementById('shortcutHelpModal');
        var modal = new bootstrap.Modal(modalEl);
        modal.show();

        modalEl.addEventListener('hidden.bs.modal', function() {
            modalEl.remove();
        });
    }

    function initAll() {
        initRippleEffect();
        initModalEnhancements();
        initFormDirtyTracking();
        initKeyboardShortcuts();
        initDefaultShortcuts();
    }

    return {
        initAll: initAll,
        initRippleEffect: initRippleEffect,
        initModalEnhancements: initModalEnhancements,
        initFormDirtyTracking: initFormDirtyTracking,
        initKeyboardShortcuts: initKeyboardShortcuts,
        initDefaultShortcuts: initDefaultShortcuts,
        registerShortcut: registerShortcut,
        showShortcutHelp: showShortcutHelp,
        trackForm: trackForm,
        resetDirtyState: resetDirtyState,
        isFormDirty: isFormDirty
    };
})();

document.addEventListener('DOMContentLoaded', function() {
    InteractionUtils.initAll();
});
