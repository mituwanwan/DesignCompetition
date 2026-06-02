window.LoadingUtils = (function() {
    var DEFAULT_TIMEOUT = 8000;

    function safeFetch(url, options, timeout) {
        timeout = timeout || DEFAULT_TIMEOUT;
        var controller = new AbortController();
        var signal = controller.signal;
        var fetchOptions = Object.assign({}, options || {}, { signal: signal });
        var timer = setTimeout(function() {
            controller.abort();
        }, timeout);

        return fetch(url, fetchOptions).then(function(response) {
            clearTimeout(timer);
            if (!response.ok) {
                throw new Error('HTTP ' + response.status);
            }
            return response.json();
        }).catch(function(err) {
            clearTimeout(timer);
            if (err.name === 'AbortError') {
                throw new Error('请求超时，请检查网络后重试');
            }
            throw err;
        });
    }

    function showLoading(container, message) {
        if (!container) return;
        message = message || '正在加载...';
        container.innerHTML =
            '<div class="state-placeholder state-loading">' +
                '<i class="bi bi-hourglass-split"></i>' +
                '<p>' + message + '</p>' +
            '</div>';
    }

    function showEmpty(container, message) {
        if (!container) return;
        message = message || '暂无数据';
        container.innerHTML =
            '<div class="state-placeholder state-empty">' +
                '<i class="bi bi-inbox"></i>' +
                '<p>' + message + '</p>' +
            '</div>';
    }

    function showError(container, message, retryCallback) {
        if (!container) return;
        message = message || '加载失败，请刷新重试';
        var retryBtn = '';
        if (typeof retryCallback === 'function') {
            var btnId = 'retry-btn-' + Math.random().toString(36).substr(2, 9);
            retryBtn = '<button class="btn btn-sm btn-outline-primary mt-2 state-retry-btn" id="' + btnId + '"><i class="bi bi-arrow-clockwise me-1"></i>重新加载</button>';
            container.innerHTML =
                '<div class="state-placeholder state-error">' +
                    '<i class="bi bi-exclamation-circle"></i>' +
                    '<p>' + message + '</p>' +
                    retryBtn +
                '</div>';
            var btn = document.getElementById(btnId);
            if (btn) {
                btn.addEventListener('click', function() {
                    retryCallback();
                });
            }
        } else {
            container.innerHTML =
                '<div class="state-placeholder state-error">' +
                    '<i class="bi bi-exclamation-circle"></i>' +
                    '<p>' + message + '</p>' +
                '</div>';
        }
    }

    function wrapFetch(container, url, options, loadingMessage, emptyMessage) {
        if (container) {
            showLoading(container, loadingMessage);
        }
        return safeFetch(url, options)
            .then(function(data) {
                if (data && data.code === 200) {
                    return data;
                } else {
                    throw new Error(data && data.msg ? data.msg : '请求失败');
                }
            })
            .catch(function(err) {
                if (container) {
                    var retryFn = function() {
                        wrapFetch(container, url, options, loadingMessage, emptyMessage);
                    };
                    showError(container, err.message || '加载失败，请刷新重试', retryFn);
                }
                throw err;
            });
    }

    return {
        safeFetch: safeFetch,
        showLoading: showLoading,
        showEmpty: showEmpty,
        showError: showError,
        wrapFetch: wrapFetch,
        DEFAULT_TIMEOUT: DEFAULT_TIMEOUT
    };
})();
