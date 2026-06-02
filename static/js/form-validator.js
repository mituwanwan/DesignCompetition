window.FormValidator = (function() {
    var validators = {
        required: function(value) {
            if (value === null || value === undefined) return '此字段为必填项';
            if (typeof value === 'string' && value.trim() === '') return '此字段为必填项';
            return null;
        },
        minLength: function(value, min) {
            if (!value) return null;
            if (value.length < min) return '至少需要输入' + min + '个字符，当前已输入' + value.length + '个';
            return null;
        },
        maxLength: function(value, max) {
            if (!value) return null;
            if (value.length > max) return '最多输入' + max + '个字符，当前已输入' + value.length + '个，请精简内容';
            return null;
        },
        pattern: function(value, regex, message) {
            if (!value) return null;
            if (!regex.test(value)) return message || '输入格式不正确';
            return null;
        },
        email: function(value) {
            if (!value) return null;
            var re = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;
            if (!re.test(value)) return '请输入有效的邮箱地址，例如 user@example.com';
            return null;
        },
        phone: function(value) {
            if (!value) return null;
            var re = /^1[3-9]\d{9}$/;
            if (!re.test(value)) return '请输入有效的手机号码，11位数字，以1开头';
            return null;
        },
        number: function(value) {
            if (!value) return null;
            if (isNaN(value) || value.trim() === '') return '请输入有效的数字';
            return null;
        },
        min: function(value, minVal) {
            if (!value && value !== 0) return null;
            var num = parseFloat(value);
            if (isNaN(num)) return '请输入有效的数字';
            if (num < minVal) return '数值不能小于' + minVal;
            return null;
        },
        max: function(value, maxVal) {
            if (!value && value !== 0) return null;
            var num = parseFloat(value);
            if (isNaN(num)) return '请输入有效的数字';
            if (num > maxVal) return '数值不能大于' + maxVal;
            return null;
        },
        range: function(value, minVal, maxVal) {
            if (!value && value !== 0) return null;
            var num = parseFloat(value);
            if (isNaN(num)) return '请输入' + minVal + '到' + maxVal + '之间的数值';
            if (num < minVal || num > maxVal) return '请输入' + minVal + '到' + maxVal + '之间的数值';
            return null;
        },
        password: function(value) {
            if (!value) return null;
            if (value.length < 8) return '密码至少需要8位字符';
            if (!/[a-z]/.test(value)) return '密码需包含至少一个小写字母';
            if (!/[A-Z]/.test(value)) return '密码需包含至少一个大写字母';
            if (!/[0-9]/.test(value)) return '密码需包含至少一个数字';
            return null;
        },
        confirmPassword: function(value, selector) {
            if (!value) return null;
            var target = document.querySelector(selector);
            if (!target) return null;
            if (value !== target.value) return '两次输入的密码不一致，请重新确认';
            return null;
        },
        url: function(value) {
            if (!value) return null;
            try {
                new URL(value);
                return null;
            } catch (e) {
                return '请输入有效的URL地址，例如 https://example.com';
            }
        },
        date: function(value) {
            if (!value) return null;
            var d = new Date(value);
            if (isNaN(d.getTime())) return '请输入有效的日期';
            return null;
        },
        idCard: function(value) {
            if (!value) return null;
            var re = /(^\d{15}$)|(^\d{18}$)|(^\d{17}(\d|X|x)$)/;
            if (!re.test(value)) return '请输入有效的身份证号码（15位或18位）';
            return null;
        }
    };

    function validateField(input, rules) {
        var value = input.value;
        var error = null;

        for (var i = 0; i < rules.length; i++) {
            var rule = rules[i];
            var ruleName = typeof rule === 'string' ? rule : rule.rule;
            var validatorFn = validators[ruleName];

            if (!validatorFn) continue;

            if (typeof rule === 'string') {
                error = validatorFn(value);
            } else {
                var args = [value].concat(rule.args || []);
                error = validatorFn.apply(null, args);
            }

            if (error) break;
        }

        updateFieldState(input, error);
        return error;
    }

    function updateFieldState(input, error) {
        var feedbackEl = input.parentElement.querySelector('.invalid-feedback') ||
                         input.closest('.mb-3, .form-group')?.querySelector('.invalid-feedback');

        input.classList.remove('is-valid', 'is-invalid');

        if (error) {
            input.classList.add('is-invalid');
            if (feedbackEl) {
                feedbackEl.textContent = error;
                feedbackEl.style.display = 'block';
            }
        } else if (input.value.trim() !== '') {
            input.classList.add('is-valid');
            if (feedbackEl) {
                feedbackEl.style.display = 'none';
            }
        } else {
            if (feedbackEl) {
                feedbackEl.style.display = 'none';
            }
        }
    }

    function setupForm(formSelector, fieldRules) {
        var form = document.querySelector(formSelector);
        if (!form) return;

        Object.keys(fieldRules).forEach(function(selector) {
            var input = form.querySelector(selector);
            if (!input) return;

            var rules = fieldRules[selector];

            if (!input.parentElement.querySelector('.invalid-feedback')) {
                var feedback = document.createElement('div');
                feedback.className = 'invalid-feedback';
                input.parentElement.appendChild(feedback);
            }

            var debounceTimer;
            input.addEventListener('input', function() {
                clearTimeout(debounceTimer);
                debounceTimer = setTimeout(function() {
                    if (input.classList.contains('is-invalid') || input.value.trim() !== '') {
                        validateField(input, rules);
                    }
                }, 300);
            });

            input.addEventListener('blur', function() {
                if (input.value.trim() !== '') {
                    validateField(input, rules);
                }
            });
        });
    }

    function validateForm(formSelector, fieldRules) {
        var form = document.querySelector(formSelector);
        if (!form) return false;

        var isValid = true;
        var firstInvalid = null;

        Object.keys(fieldRules).forEach(function(selector) {
            var input = form.querySelector(selector);
            if (!input) return;

            var error = validateField(input, fieldRules[selector]);
            if (error) {
                isValid = false;
                if (!firstInvalid) firstInvalid = input;
            }
        });

        if (firstInvalid) {
            firstInvalid.focus();
            firstInvalid.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }

        return isValid;
    }

    function resetForm(formSelector) {
        var form = document.querySelector(formSelector);
        if (!form) return;

        form.querySelectorAll('.is-valid, .is-invalid').forEach(function(el) {
            el.classList.remove('is-valid', 'is-invalid');
        });

        form.querySelectorAll('.invalid-feedback').forEach(function(el) {
            el.style.display = 'none';
        });
    }

    return {
        validators: validators,
        validateField: validateField,
        setupForm: setupForm,
        validateForm: validateForm,
        resetForm: resetForm
    };
})();
