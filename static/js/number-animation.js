window.NumberAnimation = (function() {
    var defaultDuration = 800;
    var defaultEasing = 'easeOutExpo';

    var easings = {
        linear: function(t) { return t; },
        easeOutQuad: function(t) { return t * (2 - t); },
        easeOutExpo: function(t) { return t === 1 ? 1 : 1 - Math.pow(2, -10 * t); },
        easeOutCubic: function(t) { return 1 - Math.pow(1 - t, 3); },
        easeOutBounce: function(t) {
            if (t < 1 / 2.75) return 7.5625 * t * t;
            if (t < 2 / 2.75) return 7.5625 * (t -= 1.5 / 2.75) * t + 0.75;
            if (t < 2.5 / 2.75) return 7.5625 * (t -= 2.25 / 2.75) * t + 0.9375;
            return 7.5625 * (t -= 2.625 / 2.75) * t + 0.984375;
        }
    };

    function animateValue(element, startVal, endVal, options) {
        options = options || {};

        if (typeof element === 'string') {
            element = document.getElementById(element);
        }
        if (!element) return;

        var duration = options.duration || defaultDuration;
        var easingName = options.easing || defaultEasing;
        var easingFn = easings[easingName] || easings[defaultEasing];
        var decimals = options.decimals !== undefined ? options.decimals : getDecimals(endVal);
        var prefix = options.prefix || '';
        var suffix = options.suffix || '';
        var separator = options.separator || '';
        var onComplete = options.onComplete || null;

        startVal = parseFloat(startVal) || 0;
        endVal = parseFloat(endVal);

        if (isNaN(endVal)) {
            element.textContent = prefix + '--' + suffix;
            return;
        }

        if (startVal === endVal) {
            element.textContent = prefix + formatNumber(endVal, decimals, separator) + suffix;
            return;
        }

        var startTime = null;
        var rafId;

        function step(timestamp) {
            if (!startTime) startTime = timestamp;
            var progress = Math.min((timestamp - startTime) / duration, 1);
            var easedProgress = easingFn(progress);
            var currentVal = startVal + (endVal - startVal) * easedProgress;

            element.textContent = prefix + formatNumber(currentVal, decimals, separator) + suffix;

            if (progress < 1) {
                rafId = requestAnimationFrame(step);
            } else {
                element.textContent = prefix + formatNumber(endVal, decimals, separator) + suffix;
                if (onComplete) onComplete(endVal);
            }
        }

        if (rafId) cancelAnimationFrame(rafId);
        rafId = requestAnimationFrame(step);

        return {
            cancel: function() {
                if (rafId) cancelAnimationFrame(rafId);
            }
        };
    }

    function getDecimals(value) {
        if (value === Math.floor(value)) return 0;
        var str = value.toString();
        var dotIndex = str.indexOf('.');
        return dotIndex >= 0 ? str.length - dotIndex - 1 : 0;
    }

    function formatNumber(num, decimals, separator) {
        var fixed = num.toFixed(decimals);
        if (!separator) return fixed;

        var parts = fixed.split('.');
        parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, separator);
        return parts.join('.');
    }

    function animateAllCards(selector, dataMap, options) {
        selector = selector || '.stat-num, .display-4, .display-6, [data-animate-count]';
        options = options || {};

        var elements = document.querySelectorAll(selector);
        elements.forEach(function(el) {
            var key = el.id || el.getAttribute('data-count-key');
            if (!key || dataMap[key] === undefined) return;

            var currentValue = parseFloat(el.textContent.replace(/[^0-9.\-]/g, '')) || 0;
            var targetValue = dataMap[key];

            var elOptions = Object.assign({}, options);
            var decimalsAttr = el.getAttribute('data-decimals');
            if (decimalsAttr !== null) elOptions.decimals = parseInt(decimalsAttr);

            var suffixAttr = el.getAttribute('data-suffix');
            if (suffixAttr) elOptions.suffix = suffixAttr;

            var prefixAttr = el.getAttribute('data-prefix');
            if (prefixAttr) elOptions.prefix = prefixAttr;

            animateValue(el, currentValue, targetValue, elOptions);
        });
    }

    function initIntersectionObserver(selector, callback) {
        selector = selector || '.stat-num, .display-4, .display-6, [data-animate-count]';

        if (!('IntersectionObserver' in window)) {
            if (callback) callback();
            return;
        }

        var observer = new IntersectionObserver(function(entries) {
            entries.forEach(function(entry) {
                if (entry.isIntersecting) {
                    observer.unobserve(entry.target);
                    if (callback) callback(entry.target);
                }
            });
        }, { threshold: 0.3 });

        document.querySelectorAll(selector).forEach(function(el) {
            observer.observe(el);
        });
    }

    return {
        animateValue: animateValue,
        animateAllCards: animateAllCards,
        initIntersectionObserver: initIntersectionObserver,
        easings: easings
    };
})();
