/**
 * 智慧养老院管理系统 - 认证相关JavaScript功能
 */

// 配置
const AuthConfig = {
    rememberKey: 'nursing_home_remember_username',
    sessionTimeout: 30 * 60 * 1000, // 30分钟
    apiEndpoints: {
        login: '/api/v1/auth/login',
        logout: '/api/v1/auth/logout',
        checkSession: '/api/v1/auth/session'
    }
};

/**
 * 认证管理类
 */
class AuthManager {
    constructor() {
        this.init();
    }

    /**
     * 初始化认证管理器
     */
    init() {
        this.setupRememberMe();
        this.setupRoleSelection();
        this.setupFormValidation();
        this.checkSessionTimeout();
    }

    /**
     * 设置"记住我"功能
     */
    setupRememberMe() {
        const rememberCheckbox = document.getElementById('rememberMe');
        const usernameInput = document.getElementById('username');

        if (!rememberCheckbox || !usernameInput) return;

        // 检查是否有保存的用户名
        const savedUsername = localStorage.getItem(AuthConfig.rememberKey);
        if (savedUsername) {
            usernameInput.value = savedUsername;
            rememberCheckbox.checked = true;
        }

        // 监听记住我状态变化
        rememberCheckbox.addEventListener('change', function() {
            if (!this.checked) {
                localStorage.removeItem(AuthConfig.rememberKey);
            }
        });
    }

    /**
     * 设置角色选择交互
     */
    setupRoleSelection() {
        const roleSelect = document.getElementById('role');
        const roleOptions = document.querySelectorAll('.role-option');

        if (!roleSelect && roleOptions.length === 0) return;

        // 如果是下拉框模式
        if (roleSelect) {
            roleSelect.addEventListener('change', function() {
                this.classList.toggle('selected', this.value !== '');
            });
        }

        // 如果是卡片选择模式
        roleOptions.forEach(option => {
            option.addEventListener('click', function() {
                const role = this.dataset.role;
                const roleSelect = document.getElementById('role');

                // 移除其他选项的选中状态
                roleOptions.forEach(opt => opt.classList.remove('selected'));

                // 设置当前选项为选中状态
                this.classList.add('selected');

                // 更新隐藏的select元素
                if (roleSelect) {
                    roleSelect.value = role;
                }
            });
        });
    }

    /**
     * 设置表单验证
     */
    setupFormValidation() {
        const loginForm = document.getElementById('loginForm');
        if (!loginForm) return;

        if (window.FormValidator) {
            FormValidator.setupForm('#loginForm', {
                '#username': ['required', { rule: 'minLength', args: [2] }],
                '#password': ['required', { rule: 'minLength', args: [6] }],
                '#role': ['required']
            });
        } else {
            const inputs = loginForm.querySelectorAll('input[required], select[required]');

            inputs.forEach(input => {
                input.addEventListener('blur', function() {
                    this.classList.toggle('is-invalid', !this.checkValidity());
                    this.classList.toggle('is-valid', this.checkValidity() && this.value.trim() !== '');
                });

                input.addEventListener('input', function() {
                    if (this.classList.contains('is-invalid')) {
                        this.classList.remove('is-invalid');
                    }
                });
            });
        }
    }

    /**
     * 处理登录表单提交
     */
    async handleLogin(event) {
        event.preventDefault();

        const form = event.target;
        const submitBtn = form.querySelector('button[type="submit"]');
        const errorMsg = document.getElementById('errorMsg');
        const rememberCheckbox = document.getElementById('rememberMe');

        // 验证表单
        if (!form.checkValidity()) {
            form.classList.add('was-validated');
            this.hideLoading(submitBtn); // 恢复按钮状态
            return false;
        }

        // 获取表单数据
        const formData = {
            username: document.getElementById('username').value.trim(),
            password: document.getElementById('password').value,
            role: document.getElementById('role').value
        };

        // 验证必填字段
        if (!formData.role) {
            this.showError('请选择您的角色');
            this.hideLoading(submitBtn); // 恢复按钮状态
            return false;
        }

        // 显示加载状态
        this.showLoading(submitBtn);
        if (errorMsg) errorMsg.classList.remove('show');

        try {
            // 发送登录请求
            const response = await fetch(AuthConfig.apiEndpoints.login, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    username: formData.username,
                    password: formData.password
                })
            });

            const data = await response.json();

            // 隐藏加载状态
            this.hideLoading(submitBtn);

            if (data.code === 200) {
                // 登录成功
                if (rememberCheckbox && rememberCheckbox.checked) {
                    localStorage.setItem(AuthConfig.rememberKey, formData.username);
                }

                // 根据角色重定向
                const role = data.data.role || formData.role;
                this.redirectToDashboard(role);
            } else {
                // 登录失败
                this.showError(data.msg || '登录失败，请检查用户名和密码');
            }
        } catch (error) {
            // 隐藏加载状态
            this.hideLoading(submitBtn);

            console.error('登录请求失败:', error);
            this.showError('网络连接失败，请检查后端服务是否正常运行');
        }

        return false;
    }

    /**
     * 根据角色重定向到对应的仪表盘
     */
    redirectToDashboard(role) {
        const redirectUrls = {
            admin: '/admin',
            caregiver: '/caregiver',
            family: '/family'
        };

        const redirectUrl = redirectUrls[role];
        if (redirectUrl) {
            // 添加一个小延迟让用户看到成功状态
            setTimeout(() => {
                window.location.href = redirectUrl;
            }, 300);
        } else {
            this.showError('未知的用户角色，请联系管理员');
        }
    }

    /**
     * 显示错误消息
     */
    showError(message) {
        const errorEl = document.getElementById('errorMsg');
        if (errorEl) {
            errorEl.textContent = message;
            errorEl.classList.add('show');

            // 滚动到错误消息位置
            errorEl.scrollIntoView({ behavior: 'smooth', block: 'center' });

            // 5秒后自动隐藏
            setTimeout(() => {
                errorEl.classList.remove('show');
            }, 5000);
        } else {
            alert(message); // 备用方案
        }
    }

    /**
     * 显示加载状态
     */
    showLoading(button) {
        if (button) {
            button.disabled = true;
            button.classList.add('loading');
            button.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> 登录中...';
        }
    }

    /**
     * 隐藏加载状态
     */
    hideLoading(button) {
        if (button) {
            button.disabled = false;
            button.classList.remove('loading');
            button.textContent = '立即登录';
        }
    }

    /**
     * 检查会话超时
     */
    checkSessionTimeout() {
        // 定期检查会话状态（如果已登录）
        if (document.body.classList.contains('authenticated')) {
            setInterval(() => {
                fetch(AuthConfig.apiEndpoints.checkSession)
                    .then(res => res.json())
                    .then(data => {
                        if (data.code !== 200) {
                            this.handleSessionTimeout();
                        }
                    })
                    .catch(() => {
                        // 忽略网络错误
                    });
            }, AuthConfig.sessionTimeout);
        }
    }

    /**
     * 处理会话超时
     */
    handleSessionTimeout() {
        // 清除本地存储
        localStorage.removeItem(AuthConfig.rememberKey);

        // 显示超时提示
        const timeoutModal = new bootstrap.Modal(document.getElementById('sessionTimeoutModal'));
        timeoutModal.show();

        // 5秒后自动跳转到登录页
        setTimeout(() => {
            window.location.href = '/login';
        }, 5000);
    }

    /**
     * 处理退出登录
     */
    async handleLogout() {
        try {
            const response = await fetch(AuthConfig.apiEndpoints.logout, {
                method: 'POST'
            });

            const data = await response.json();

            if (data.code === 200) {
                // 清除本地存储
                localStorage.removeItem(AuthConfig.rememberKey);

                // 重定向到登录页
                window.location.href = '/login';
            }
        } catch (error) {
            console.error('退出登录失败:', error);
            // 即使API失败也清除本地状态并重定向
            localStorage.removeItem(AuthConfig.rememberKey);
            window.location.href = '/login';
        }
    }

    /**
     * 重置表单
     */
    resetForm() {
        const form = document.getElementById('loginForm');
        if (form) {
            form.reset();
            form.classList.remove('was-validated');

            // 清除验证状态
            const inputs = form.querySelectorAll('input, select');
            inputs.forEach(input => {
                input.classList.remove('is-valid', 'is-invalid');
            });

            // 清除错误消息
            const errorMsg = document.getElementById('errorMsg');
            if (errorMsg) {
                errorMsg.classList.remove('show');
            }
        }
    }
}

/**
 * 页面加载完成后初始化
 */
document.addEventListener('DOMContentLoaded', function() {
    // 初始化认证管理器
    window.authManager = new AuthManager();

    // 绑定登录表单提交事件
    const loginForm = document.getElementById('loginForm');
    if (loginForm) {
        loginForm.addEventListener('submit', function(e) {
            window.authManager.handleLogin(e);
        });
    }

    // 绑定登录按钮点击事件（备用）
    const loginBtn = document.getElementById('loginBtn');
    if (loginBtn && !loginForm) {
        loginBtn.addEventListener('click', function(e) {
            window.authManager.handleLogin(e);
        });
    }

    // 绑定退出登录按钮
    const logoutBtn = document.getElementById('logoutBtn');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', function() {
            if (confirm('确定要退出登录吗？')) {
                window.authManager.handleLogout();
            }
        });
    }

    // 绑定重置按钮
    const resetBtn = document.getElementById('resetBtn');
    if (resetBtn) {
        resetBtn.addEventListener('click', function() {
            window.authManager.resetForm();
        });
    }

    // 绑定忘记密码链接
    const forgotPasswordLink = document.getElementById('forgotPassword');
    if (forgotPasswordLink) {
        forgotPasswordLink.addEventListener('click', function(e) {
            e.preventDefault();
            alert('忘记密码功能正在开发中，请联系管理员重置密码。');
        });
    }

    // 添加键盘快捷键支持
    document.addEventListener('keydown', function(e) {
        // Ctrl + Enter 提交表单
        if (e.ctrlKey && e.key === 'Enter') {
            const activeForm = document.querySelector('form');
            if (activeForm) {
                const submitBtn = activeForm.querySelector('button[type="submit"]');
                if (submitBtn) {
                    submitBtn.click();
                }
            }
        }

        // Esc 键重置表单
        if (e.key === 'Escape') {
            window.authManager.resetForm();
        }
    });
});

// 导出全局对象
if (typeof module !== 'undefined' && module.exports) {
    module.exports = AuthManager;
}