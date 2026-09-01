let socket = null;
let token = null;
let historyData = [];
let currentUserRole = 'admin';

const API_BASE = "http://localhost:8000";

// ========== لاگین ==========
async function login() {
    const username = document.getElementById('username').value;
    const password = document.getElementById('password').value;
    
    token = btoa(`${username}:${password}`);
    
    try {
        const response = await fetch(`${API_BASE}/stats`, {
            headers: { 'Authorization': `Basic ${token}` }
        });
        
        if (response.ok) {
            currentUserRole = username;
            if (currentUserRole === 'admin') {
                await loadUsers();
            }
            
            if (currentUserRole !== 'admin') {
                document.querySelectorAll('.edit-btn, .delete-btn, .admin-only').forEach(el => {
                    if (el) el.style.display = 'none';
                });
            }

            document.getElementById('loginContainer').style.display = 'none';
            document.getElementById('mainContainer').style.display = 'block';
            initSocket();
            loadHistory();
            loadStats();
            await loadUnitRanking();
            await loadAlertHistory();
            startAutoRefresh();

            await loadThresholdsDisplay();
            await loadRiskMatrix();
            await loadScenarios();
            await loadHazardTree();
            await loadSeverityLevels();
            await loadLikelihoodLevels();
            await loadScenarioThresholds();
        } else {
            alert("نام کاربری یا رمز عبور اشتباه است");
        }
    } catch (error) {
        alert("API در دسترس نیست. مطمئن شو python api_final.py اجرا شده است");
    }
}

// ========== نمایش فرم ثبت‌نام ==========
function showRegister() {
    document.getElementById('loginContainer').style.display = 'none';
    document.getElementById('registerContainer').style.display = 'flex';
}

function showLogin() {
    document.getElementById('registerContainer').style.display = 'none';
    document.getElementById('loginContainer').style.display = 'flex';
}

// ========== نمایش قدرت رمز عبور ==========
function checkPasswordStrength() {
    const password = document.getElementById('reg_password').value;
    const strengthDiv = document.getElementById('passwordStrength');
    let strength = 0;
    let message = '';
    let colorClass = '';
    
    if (password.length >= 8) strength++;
    if (password.match(/[a-z]/)) strength++;
    if (password.match(/[A-Z]/)) strength++;
    if (password.match(/[0-9]/)) strength++;
    if (password.match(/[^a-zA-Z0-9]/)) strength++;
    
    if (strength <= 2) {
        message = 'ضعیف';
        colorClass = 'strength-weak';
    } else if (strength <= 4) {
        message = 'متوسط';
        colorClass = 'strength-medium';
    } else {
        message = 'قوی';
        colorClass = 'strength-strong';
    }
    
    strengthDiv.innerHTML = `قدرت رمز: <span class="${colorClass}">${message}</span>`;
}

// ========== ثبت‌نام ==========
async function register() {
    const fullname = document.getElementById('reg_fullname').value;
    const personnel_code = document.getElementById('reg_personnel_code').value;
    const phone = document.getElementById('reg_phone').value;
    const username = document.getElementById('reg_username').value;
    const password = document.getElementById('reg_password').value;
    const confirm_password = document.getElementById('reg_confirm_password').value;
    
    if (!fullname || !personnel_code || !phone || !username || !password || !confirm_password) {
        alert("لطفاً همه فیلدها را پر کنید");
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/register`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                fullname, personnel_code, phone, username, password, confirm_password
            })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            alert(`✅ ثبت‌نام موفق!\nنام کاربری: ${data.username}\nسطح دسترسی: اپراتور`);
            showLogin();
            document.getElementById('username').value = username;
        } else {
            alert(`❌ خطا: ${data.detail}`);
        }
    } catch (error) {
        alert("خطا در ارتباط با سرور");
    }
}

// اتصال رویداد قدرت رمز
document.addEventListener('DOMContentLoaded', () => {
    const passwordInput = document.getElementById('reg_password');
    if (passwordInput) {
        passwordInput.addEventListener('input', checkPasswordStrength);
    }
});

// ========== WebSocket ==========
function initSocket() {
    socket = io(API_BASE, {
        transports: ['websocket'],
        path: '/socket.io/'
    });
    
    socket.on('connect', () => {
        console.log('WebSocket متصل شد');
        const statusEl = document.getElementById('connectionStatus');
        if (statusEl) statusEl.innerHTML = '🟢 آنلاین';
    });
    
    socket.on('disconnect', () => {
        const statusEl = document.getElementById('connectionStatus');
        if (statusEl) statusEl.innerHTML = '🔴 آفلاین';
    });
    
    socket.on('new_prediction', (data) => {
        console.log('پیش‌بینی جدید:', data);
        addToHistory(data);
        updateLastAlert(data);
    });
    
    socket.on('sensor_data', (data) => {
        const updateEl = document.getElementById('lastUpdate');
        if (updateEl) {
            updateEl.innerHTML = `📡 آخرین داده سنسور: ${data.temperature}°C | ${data.pressure} bar | ریسک: ${getRiskText(data.risk_level)}`;
        }
    });
}

// ========== پیش‌بینی دستی ==========
async function manualPredict() {
    const temp = parseFloat(document.getElementById('temp').value);
    const press = parseFloat(document.getElementById('press').value);
    const flow = parseFloat(document.getElementById('flow').value);
    const level = parseFloat(document.getElementById('level').value);
    
    if (isNaN(temp) || isNaN(press) || isNaN(flow) || isNaN(level)) {
        alert("لطفاً همه مقادیر را وارد کنید");
        return;
    }
    
    const resultBox = document.getElementById('result');
    resultBox.classList.remove('hidden', 'red-bg', 'yellow-bg', 'green-bg');
    resultBox.innerHTML = "⏳ در حال پیش‌بینی...";
    resultBox.classList.add('visible');
    
    try {
        const response = await fetch(`${API_BASE}/predict`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Basic ${token}`
            },
            body: JSON.stringify({
                temperature: temp,
                pressure: press,
                flow_rate: flow,
                level: level
            })
        });
        
        const data = await response.json();
        
        let riskText = "";
        if (data.risk_level === 2) riskText = "🔴 ریسک بالا (High)";
        else if (data.risk_level === 1) riskText = "🟡 ریسک متوسط (Medium)";
        else riskText = "🟢 ریسک کم (Low)";resultBox.innerHTML = `${riskText}<br>اعتماد: ${Math.round(data.confidence*100)}%<br>📌 ${data.root_cause}`;
        
        if (data.risk_level === 2) resultBox.classList.add('red-bg');
        else if (data.risk_level === 1) resultBox.classList.add('yellow-bg');
        else resultBox.classList.add('green-bg');
        
        loadHistory();
        loadStats();
        
    } catch (error) {
        resultBox.innerHTML = "❌ خطا در ارتباط با سرور";
        resultBox.classList.add('red-bg');
    }
}

// ========== بارگذاری تاریخچه ==========
async function loadHistory() {
    try {
        const response = await fetch(`${API_BASE}/history`, {
            headers: { 'Authorization': `Basic ${token}` }
        });
        const data = await response.json();
        historyData = data;
        
        const tbody = document.querySelector('#historyTable tbody');
        if (!tbody) return;
        tbody.innerHTML = '';
        
        for (let row of data.slice(0, 20)) {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>${new Date(row.created_at).toLocaleTimeString('fa-IR')}</td>
                <td>${row.temperature.toFixed(1)}°C}(
                <td>${row.pressure.toFixed(2)} bar}(
                <td class="${row.risk_level === 2 ? 'risk-high-text' : (row.risk_level === 1 ? 'risk-medium-text' : 'risk-low-text')}">
                    ${row.risk_level === 2 ? '🔴 بالا' : (row.risk_level === 1 ? '🟡 متوسط' : '🟢 کم')}
                 </td>
                <td>${(row.root_cause || '').substring(0, 50)}}(
            `;
            tbody.appendChild(tr);
        }
    } catch (error) {
        console.log("خطا در بارگذاری تاریخچه");
    }
}

//نمودار دایره ای
function drawPieChart(low, medium, high) {
    const canvas = document.getElementById('riskPieChart');
    if (!canvas) return;
    
    const ctx = canvas.getContext('2d');
    const total = low + medium + high;
    if (total === 0) return;
    
    const width = canvas.width;
    const height = canvas.height;
    ctx.clearRect(0, 0, width, height);
    
    const angles = [
        (low / total) * 2 * Math.PI,
        (medium / total) * 2 * Math.PI,
        (high / total) * 2 * Math.PI
    ];
    
    const colors = ['#2e7d32', '#f57f17', '#c62828'];
    let startAngle = -Math.PI / 2;
    
    for (let i = 0; i < 3; i++) {
        const endAngle = startAngle + angles[i];
        ctx.beginPath();
        ctx.fillStyle = colors[i];
        ctx.moveTo(width/2, height/2);
        ctx.arc(width/2, height/2, width/2 - 5, startAngle, endAngle);
        ctx.fill();
        startAngle = endAngle;
    }
    
    ctx.fillStyle = '#fff';
    ctx.font = 'bold 14px Tahoma';
    ctx.fillText(`🟢 کم: ${low}`, 10, 30);
    ctx.fillStyle = '#f57f17';
    ctx.fillText(`🟡 متوسط: ${medium}`, 10, 55);
    ctx.fillStyle = '#c62828';
    ctx.fillText(`🔴 بالا: ${high}`, 10, 80);
}
// ========== بارگذاری آمار ==========
async function loadStats() {
    try {
        const response = await fetch(`${API_BASE}/stats`, {
            headers: { 'Authorization': `Basic ${token}` }
        });
        const stats = await response.json();
        
        const total = stats.low + stats.medium + stats.high;
        const statsDiv = document.getElementById('stats');
        if (!statsDiv) return;
       
        statsDiv.innerHTML = `
            <div class="stat-item">
                <div class="stat-number stat-low">${stats.low}</div>
                <div class="stat-label">🟢 ریسک کم</div>
            </div>
            <div class="stat-item">
                <div class="stat-number stat-medium">${stats.medium}</div>
                <div class="stat-label">🟡 ریسک متوسط</div>
            </div>
            <div class="stat-item">
                <div class="stat-number stat-high">${stats.high}</div>
                <div class="stat-label">🔴 ریسک بالا</div>
            </div>
            <div style="clear:both"></div>
            <div class="stat-label" style="text-align:center; margin-top:15px;">مجموع پیش‌بینی‌ها: ${total}</div>
        `;
        drawPieChart(stats.low, stats.medium, stats.high);
    } catch (error) {
        console.log("خطا در بارگذاری آمار");
    }
}

// ========== بروزرسانی لحظه‌ای ==========
function addToHistory(data) {
    const tbody = document.querySelector('#historyTable tbody');
    if (!tbody) return;
    const tr = document.createElement('tr');
    tr.innerHTML = `
        <td>${new Date(data.timestamp).toLocaleTimeString('fa-IR')}(
        <td>-}(
        <td>-}(
        <td class="${data.risk_level === 2 ? 'risk-high-text' : (data.risk_level === 1 ? 'risk-medium-text' : 'risk-low-text')}">
            ${data.risk_level === 2 ? '🔴 بالا' : (data.risk_level === 1 ? '🟡 متوسط' : '🟢 کم')}
         </td>
        <td>${data.root_cause?.substring(0, 50) || '-'}(
    `;
    tbody.insertBefore(tr, tbody.firstChild);
    if (tbody.children.length > 20) tbody.removeChild(tbody.lastChild);
    
    loadStats();
}

function updateLastAlert(data) {
    const alertDiv = document.getElementById('lastAlert');
    if (!alertDiv) return;
    if (data.risk_level === 2) {
        alertDiv.innerHTML = `🔴 هشدار بحرانی! ریسک بالا detected در ${new Date(data.timestamp).toLocaleTimeString('fa-IR')}<br>علت: ${data.root_cause}`;
        alertDiv.className = 'alert-critical';
    } else if (data.risk_level === 1) {
        alertDiv.innerHTML = `🟡 هشدار: ریسک متوسط - نیاز به بررسی`;
        alertDiv.className = 'alert-warning';
    } else {
        alertDiv.innerHTML = `✅ وضعیت عادی - همه پارامترها در محدوده ایمن`;
        alertDiv.className = 'alert-normal';
    }
}

function getRiskText(risk) {
    return risk === 2 ? 'پرخطر' : (risk === 1 ? 'متوسط' : 'کم‌خطر');
}

// ========== PDF ==========
// ========== دانلود گزارش کامل PDF (با چاپ مرورگر) ==========
function downloadFullPDF() {
    const originalContainer = document.getElementById('mainContainer');
    if (!originalContainer) {
        alert("خطا: محتوای گزارش یافت نشد");
        return;
    }

    // کپی از کل محتوای داشبورد
    const cloneContainer = originalContainer.cloneNode(true);
    cloneContainer.style.position = 'absolute';
    cloneContainer.style.top = '0';
    cloneContainer.style.left = '0';
    cloneContainer.style.width = '100%';
    cloneContainer.style.backgroundColor = 'white';
    cloneContainer.style.padding = '20px';
    cloneContainer.style.zIndex = '9999';
    
    // حذف دکمه‌ها و فوتر از نسخه چاپی
    const buttons = cloneContainer.querySelectorAll('button');
    buttons.forEach(btn => btn.remove());
    const footer = cloneContainer.querySelector('.footer-custom');
    if (footer) footer.remove();
    
    document.body.appendChild(cloneContainer);
    
    // باز کردن پنجره چاپ
    window.print();
    
    // حذف کپی بعد از چاپ
    setTimeout(() => {
        document.body.removeChild(cloneContainer);
    }, 1000);
}

// اتصال دکمه به تابع
document.addEventListener('DOMContentLoaded', () => {
    const pdfBtn = document.getElementById('fullPdfBtn');
    if (pdfBtn) {
        pdfBtn.addEventListener('click', downloadFullPDF);
    }
});
// ==========Excel خروجی =========
async function exportExcel() {
    try {
        window.open(`${API_BASE}/export-excel?token=${token}`, '_blank');
    } catch (error) {
        alert("خطا در خروجی Excel");
    }
}
//===========پشتیبانی از دیتابیس =======
async function backupDatabase() {
    if (currentUserRole !== 'admin') {
        alert("⛔ فقط ادمین می‌تواند پشتیبان بگیرد");
        return;
    }
    
    try {
        window.open(`${API_BASE}/backup-db?token=${token}`, '_blank');
    } catch (error) {
        alert("خطا در گرفتن پشتیبان");
    }
}
// ========== مدیریت کاربران (فقط ادمین) ==========
async function loadUsers() {
    if (currentUserRole !== 'admin') return;
    
    try {
        const response = await fetch(`${API_BASE}/admin/users`, {
            headers: { 'Authorization': `Basic ${token}` }
        });
        const users = await response.json();
        
        const tbody = document.querySelector('#usersTable tbody');
        if (!tbody) return;
        tbody.innerHTML = '';
        
        for (const user of users) {
            if (user.username === 'admin') continue; // ادمین اصلی را نمایش نده
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>${user.username}</td>
                <td>${user.fullname || '-'}</td>
                <td>${user.personnel_code || '-'}</td>
                <td>${user.phone || '-'}</td>
                <td>${user.created_at ? new Date(user.created_at).toLocaleDateString('fa-IR') : '-'}</td>
                <td><button onclick="deleteUser('${user.username}')" style="background:#c62828; padding:5px 10px;">🗑️ حذف</button>}(
            `;
            tbody.appendChild(tr);
        }
        
        // نمایش کارت مدیریت کاربران فقط برای ادمین
        const userCard = document.getElementById('userManagementCard');
        if (userCard) userCard.style.display = 'block';
        
    } catch (error) {
        console.log("خطا در بارگذاری کاربران:", error);
    }
}

async function createOperator() {
    const fullname = document.getElementById('new_fullname').value;
    const personnel_code = document.getElementById('new_personnel_code').value;
    const phone = document.getElementById('new_phone').value;
    const username = document.getElementById('new_username').value;
    const password = document.getElementById('new_password').value;
    
    if (!fullname || !personnel_code || !phone || !username || !password) {
        alert("لطفاً همه فیلدها را پر کنید");
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/admin/users`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Basic ${token}`
            },
            body: JSON.stringify({ fullname, personnel_code, phone, username, password })
        });
        
        const data = await response.json();
        if (response.ok) {
            alert("✅ اپراتور جدید اضافه شد");
            document.getElementById('new_fullname').value = '';
            document.getElementById('new_personnel_code').value = '';
            document.getElementById('new_phone').value = '';
            document.getElementById('new_username').value = '';
            document.getElementById('new_password').value = '';
            loadUsers();
        } else {
            alert(`❌ خطا: ${data.detail}`);
        }
    } catch (error) {
        alert("خطا در ارتباط با سرور");
    }
}

async function deleteUser(username) {
    if (!confirm(`آیا از حذف کاربر "${username}" مطمئن هستید؟`)) return;
    
    try {
        const response = await fetch(`${API_BASE}/admin/users/${username}`, {
            method: 'DELETE',
            headers: { 'Authorization': `Basic ${token}` }
        });
        
        if (response.ok) {
            alert(`کاربر ${username} حذف شد`);
            loadUsers();
        } else {
            const data = await response.json();
            alert(`خطا: ${data.detail}`);
        }
    } catch (error) {
        alert("خطا در ارتباط با سرور");
    }
}

// ========== خودکارسازی ==========
function startAutoRefresh() {
    setInterval(() => {
        loadHistory();
        loadStats();
    }, 30000);
}

// ========== تنظیمات آستانه ==========
async function loadThresholdsDisplay() {
    try {
        const response = await fetch(`${API_BASE}/thresholds`, {
            headers: { 'Authorization': `Basic ${token}` }
        });
        const data = await response.json();
        
        if (data.temperature) {
            const tempLow = document.getElementById('temp_low_display');
            const tempMed = document.getElementById('temp_med_display');
            const tempHigh = document.getElementById('temp_high_display');
            const pressLow = document.getElementById('press_low_display');
            const pressMed = document.getElementById('press_med_display');
            const pressHigh = document.getElementById('press_high_display');
            
            if (tempLow) tempLow.innerText = `0-${data.temperature.low_max}`;
            if (tempMed) tempMed.innerText = `${data.temperature.low_max}-${data.temperature.medium_max}`;
            if (tempHigh) tempHigh.innerText = `${data.temperature.high_min}+`;
            if (pressLow) pressLow.innerText = `0-${data.pressure.low_max}`;
            if (pressMed) pressMed.innerText = `${data.pressure.low_max}-${data.pressure.medium_max}`;
            if (pressHigh) pressHigh.innerText = `${data.pressure.high_min}+`;
        }
    } catch (error) {
        console.log("خطا در بارگذاری آستانه:", error);
    }
}

async function editThreshold(param) {
    const newLow = prompt("حداکثر مقدار برای ریسک کم (Low):");
    if (!newLow) return;
    const newMedium = prompt("حداکثر مقدار برای ریسک متوسط (Medium):");
    if (!newMedium) return;
    const newHigh = prompt("حداقل مقدار برای ریسک بالا (High):");
    if (!newHigh) return;
    
    try {
        const response = await fetch(`${API_BASE}/thresholds`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Basic ${token}`
            },
            body: JSON.stringify({
                param_name: param,
                low_max: parseFloat(newLow),
                medium_max: parseFloat(newMedium),
                high_min: parseFloat(newHigh)
            })
        });
        
        if (response.ok) {
            await loadThresholdsDisplay();
            alert(`تنظیمات ${param} با موفقیت ذخیره شد`);
        } else {
            alert("خطا در ذخیره سازی");
        }
    } catch (error) {
        alert("خطا در ارتباط با سرور");
    }
}

// ========== رتبه‌بندی واحدهای پرخطر ==========
async function loadUnitRanking() {
    try {
        const response = await fetch(`${API_BASE}/unit-ranking`, {
            headers: {'Authorization': `Basic ${token}` }
        });
        const ranking = await response.json();
        
        const container = document.getElementById('riskRanking');
        if (!container) return;
        
        if (ranking.length === 0) {
            container.innerHTML = '<div class="no-data">هیچ ریسک بالایی ثبت نشده است</div>';
            return;
        }
        
        let html = '<div class="ranking-list">';
        for (let i = 0; i < ranking.length; i++) {
            html += `
                <div class="ranking-item">
                    <span class="ranking-number">${i+1}</span>
                    <span class="ranking-cause">${ranking[i].cause}</span>
                    <span class="ranking-count">${ranking[i].count} بار</span>
                </div>
            `;
        }
        html += '</div>';
        container.innerHTML = html;
    } catch (error) {
        console.log("خطا در بارگذاری رتبه‌بندی:", error);
    }
}

// ========== تاریخچه هشدارها ==========
async function loadAlertHistory() {
    try {
        const response = await fetch(`${API_BASE}/alert-history`, {
            headers: { 'Authorization': `Basic ${token}` }
        });
        const alerts = await response.json();
        
        const list = document.getElementById('alertHistory');
        if (!list) return;
        
        if (alerts.length === 0) {
            list.innerHTML = '<li>هیچ هشدار ثبت نشده است</li>';
            return;
        }
        
        list.innerHTML = '';
        for (const alert of alerts) {
            const li = document.createElement('li');
            const riskEmoji = alert.risk_level === 2 ? '🔴' : '🟡';
            const time = new Date(alert.created_at).toLocaleTimeString('fa-IR');
            li.innerHTML = `${riskEmoji} ${time} - ${alert.root_cause.substring(0, 50)}`;
            list.appendChild(li);
        }
    } catch (error) {
        console.log("خطا در بارگذاری تاریخچه هشدارها:", error);
    }
}
//===========روند پارامتر سنسور ها =========
let sensorChart = null;
function loadSensorChart() {
    const param = document.getElementById('sensorParam').value;
    
    fetch(`${API_BASE}/history`, {
        headers: { 'Authorization': `Basic ${token}` }
    })
    .then(res => res.json())
    .then(data => {
        if (!data || data.length === 0) {
            alert("داده‌ای برای نمایش وجود ندارد");
            return;
        }
        
        const last30 = data.slice(0, 30).reverse();
        const values = last30.map(d => d[param]);
        const maxVal = Math.max(...values);
        const minVal = Math.min(...values);
        
        const canvas = document.getElementById('sensorTrendChart');
        const ctx = canvas.getContext('2d');
        const width = canvas.clientWidth;
        const height = canvas.clientHeight;
        canvas.width = width;
        canvas.height = height;
        
        ctx.clearRect(0, 0, width, height);
        
        // 1. عنوان پارامتر در بالا سمت چپ
        let paramName = "";
        if (param === 'temperature') paramName = "🌡️ دما (°C)";
        else if (param === 'pressure') paramName = "💨 فشار (bar)";
        else if (param === 'flow_rate') paramName = "💧 جریان (m³/h)";
        else if (param === 'level') paramName = "📊 سطح (%)";
        
        ctx.fillStyle = '#2F3C7E';
        ctx.font = 'bold 14px Tahoma';
        ctx.fillText(paramName, 15, 25);
        
        // 2. رنگ خط بر اساس پارامتر
        let lineColor = '#c62828';
        let fillColor = 'rgba(198, 40, 40, 0.1)';
        if (param === 'pressure') {
            lineColor = '#f57f17';
            fillColor = 'rgba(245, 127, 23, 0.1)';
        } else if (param === 'flow_rate') {
            lineColor = '#2e7d32';
            fillColor = 'rgba(46, 125, 50, 0.1)';
        } else if (param === 'level') {
            lineColor = '#1565c0';
            fillColor = 'rgba(21, 101, 192, 0.1)';
        }
        
        // 3. رسم پس‌زمینه گرادیان
        const gradient = ctx.createLinearGradient(0, 0, 0, height);
        gradient.addColorStop(0, fillColor);
        gradient.addColorStop(1, 'rgba(255,255,255,0)');
        
        // رسم محورها
        ctx.beginPath();
        ctx.strokeStyle = '#aaa';
        ctx.lineWidth = 1;
        ctx.moveTo(50, 20);
        ctx.lineTo(50, height - 30);
        ctx.lineTo(width - 20, height - 30);
        ctx.stroke();
        
        if (values.length < 2) return;
        
        const stepX = (width - 70) / (values.length - 1);
        const range = maxVal - minVal || 1;
        
        // رسم خط زیر نمودار (پر کردن زیر خط)
        ctx.beginPath();
        for (let i = 0; i < values.length; i++) {
            const x = 50 + i * stepX;
            const y = height - 30 - ((values[i] - minVal) / range) * (height - 60);
            if (i === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
        }
        ctx.lineTo(50 + (values.length - 1) * stepX, height - 30);
        ctx.lineTo(50, height - 30);
        ctx.fillStyle = gradient;
        ctx.fill();
        
        // رسم خط نمودار
        ctx.beginPath();
        ctx.strokeStyle = lineColor;
        ctx.lineWidth = 2.5;
        for (let i = 0; i < values.length; i++) {
            const x = 50 + i * stepX;
            const y = height - 30 - ((values[i] - minVal) / range) * (height - 60);
            if (i === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
        }
        ctx.stroke();
        
        // رسم نقاط روی نمودار
        for (let i = 0; i < values.length; i++) {
            const x = 50 + i * stepX;
            const y = height - 30 - ((values[i] - minVal) / range) * (height - 60);
            ctx.beginPath();
            ctx.arc(x, y, 5, 0, 2 * Math.PI);
            ctx.fillStyle = lineColor;
            ctx.fill();
            ctx.beginPath();
            ctx.arc(x, y, 2.5, 0, 2 * Math.PI);
            ctx.fillStyle = '#fff';
            ctx.fill();
        }
        
        // نوشتن مقادیر حداکثر و حداقل با باکس رنگی
        ctx.fillStyle = '#fff';
        ctx.font = 'bold 11px Tahoma';
        
        // باکس حداکثر
        ctx.fillStyle = lineColor;
        ctx.fillRect(width - 110, 15, 95, 22);
        ctx.fillStyle = '#fff';
        ctx.fillText(`🔺 حداکثر: ${maxVal.toFixed(1)}`, width - 105, 32);
        
        // باکس حداقل
        ctx.fillStyle = '#666';
        ctx.fillRect(width - 110, 42, 95, 22);
        ctx.fillStyle = '#fff';
        ctx.fillText(`🔻 حداقل: ${minVal.toFixed(1)}`, width - 105, 58);
        
        // نوشتن برچسب محور X
        ctx.fillStyle = '#666';
        ctx.font = '10px Tahoma';
        ctx.fillText('زمان →', width - 60, height - 10);
    })
    .catch(err => {
        console.error(err);
        alert("خطا در بارگذاری نمودار");
    });
}

// ========== ماتریس ریسک ۵×۵ ==========
async function loadRiskMatrix() {
    try {
        const response = await fetch(`${API_BASE}/risk-matrix`, {
            headers: { 'Authorization': `Basic ${token}` }
        });
        const data = await response.json();
        const matrix = data.matrix;
        
        let html = '<table class="matrix-table"><tr><th>احتمال / پیامد</th>';
        for (let i = 1; i <= 5; i++) html += `<th>پیامد ${i}</th>`;
        html += '</tr>';
        
        for (let p = 0; p < 5; p++) {
            html += `<tr><th>احتمال ${p+1}</th>`;
            for (let c = 0; c < 5; c++) {
                const cell = matrix[p][c];
                let cellClass = '';
                if (cell.category === 'Acceptable') cellClass = 'cell-acceptable';
                else if (cell.category === 'ALARP') cellClass = 'cell-alarp';
                else cellClass = 'cell-unacceptable';
                html += `<td class="${cellClass}">${cell.risk_level}<br>(${cell.score})</td>`;
            }
            html += '</td>';
        }
        html += '</table>';
        const matrixContainer = document.getElementById('riskMatrixTable');
        if (matrixContainer) matrixContainer.innerHTML = html;
    } catch (error) {
        console.log("خطا در بارگذاری ماتریس ریسک:", error);
    }
}

// ========== سناریوهای HAZOP ==========
async function loadScenarios() {
    try {
        const response = await fetch(`${API_BASE}/hazop-scenarios`, {
            headers: { 'Authorization': `Basic ${token}` }
        });
        const scenarios = await response.json();
        
        let html = '';
        for (const s of scenarios) {
            let riskClass = s.risk_level === 'High' ? 'scenario-risk-high' : (s.risk_level === 'Medium' ? 'scenario-risk-medium' : 'scenario-risk-low');
            html += `
                <div class="scenario-item ${riskClass}" id="scenario-${s.id}">
                    <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                        <div style="flex: 1;">
                            <strong>📌 ${s.scenario_name}</strong> (${s.node})<br>
                            ⚠️ انحراف: ${s.deviation}<br>
                            🔍 علت: ${s.cause}<br>
                            💥 پیامد: ${s.consequence}<br>
                            📊 ریسک: ${s.risk_level} | امتیاز: ${s.risk_score}<br>
                            🛠️ کنترل: ${s.mitigation || '-'}
                        </div>
                        ${currentUserRole === 'admin' ? `<button onclick="deleteScenario(${s.id})" style="background: #c62828; color: white; border: none; border-radius: 8px; padding: 8px 16px; cursor: pointer; margin-right: 10px;">🗑️ حذف</button>` : ''}
                    </div>
                </div>
            `;
        }
        const scenariosList = document.getElementById('scenariosList');
        if (scenariosList) scenariosList.innerHTML = html || '<div>هیچ سناریویی ثبت نشده است</div>';
    } catch (error) {
        console.log("خطا در بارگذاری سناریوها:", error);
    }
}

function showAddScenarioForm() {
    const form = document.getElementById('scenarioForm');
    if (form) form.style.display = 'block';
}
function hideScenarioForm() {
    const form = document.getElementById('scenarioForm');
    if (form) form.style.display = 'none';
}
async function saveScenario() {
    const data = {
        scenario_name: document.getElementById('scenario_name').value,
        node: document.getElementById('node').value,
        deviation: document.getElementById('deviation').value,
        cause: document.getElementById('cause').value,
        consequence: document.getElementById('consequence').value,
        probability: parseInt(document.getElementById('probability').value),
        consequence_severity: parseInt(document.getElementById('consequence_severity').value),
        mitigation: document.getElementById('mitigation').value
    };
    await fetch(`${API_BASE}/hazop-scenarios`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Basic ${token}` },
        body: JSON.stringify(data)
    });
    hideScenarioForm();
    loadScenarios();
    document.getElementById('scenario_name').value = '';
    document.getElementById('node').value = '';
    document.getElementById('deviation').value = '';
    document.getElementById('cause').value = '';
    document.getElementById('consequence').value = '';
    document.getElementById('mitigation').value = '';
    alert('سناریو اضافه شد');
}

async function deleteScenario(id) {
    if (confirm('آیا از حذف این سناریو مطمئن هستید؟')) {
        try {
            const response = await fetch(`${API_BASE}/hazop-scenarios/${id}`, {
                method: 'DELETE',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Basic ${token}`
                }
            });
            if (response.ok) {
                alert('سناریو با موفقیت حذف شد');
                loadScenarios();
                loadStats();
            } else {
                alert('خطا در حذف سناریو');
            }
        } catch (error) {
            console.error("خطا:", error);
            alert('خطا در ارتباط با سرور');
        }
    }
}

// ========== درخت طبقه‌بندی خطر ==========
async function loadHazardTree() {
    try {
        const response = await fetch(`${API_BASE}/hazard-tree`, {
            headers: { 'Authorization': `Basic ${token}` }
        });
        const nodes = await response.json();
        
        const children = {};
        const roots = [];
        
        for (const node of nodes) {
            if (node.parent === '0') {
                roots.push(node);
            } else {
                if (!children[node.parent]) children[node.parent] = [];
                children[node.parent].push(node);
            }
        }
        
        function renderNode(node, level = 0) {
            let html = `
                <div class="hazard-node ${level === 0 ? 'hazard-node-main' : (level === 1 ? 'hazard-node-child' : 'hazard-node-subchild')}">
                    <span class="hazard-icon">${node.icon || '📌'}</span>
                    <strong>${node.name}</strong>
                    <span class="hazard-guideword">[${node.guideword}]</span>
                    <span class="hazard-desc">${node.description}</span>
                </div>
            `;
            if (children[node.id]) {
                for (const child of children[node.id]) {
                    html += renderNode(child, level + 1);
                }
            }
            return html;
        }
        
        let html = '';
        for (const root of roots) {
            html += renderNode(root, 0);
        }
        
        const hazardTree = document.getElementById('hazardTree');
        if (hazardTree) hazardTree.innerHTML = html || '<div>درخت خطر بارگذاری نشد</div>';
    } catch (error) {
        console.log("خطا در بارگذاری درخت خطر:", error);
        const hazardTree = document.getElementById('hazardTree');
        if (hazardTree) hazardTree.innerHTML = '<div>خطا در بارگذاری</div>';
    }
}

// ========== Severity Levels ==========
async function loadSeverityLevels() {
    try {
        const response = await fetch(`${API_BASE}/severity-levels`, {
            headers: { 'Authorization': `Basic ${token}` }
        });
        const levels = await response.json();
        
        let html = '<table><tr><th>سطح</th><th>نام</th><th>اثر انسانی</th><th>خسارت مالی</th><th>زمان توقف</th></tr>';
        for (const l of levels) {
            let rowClass = l.level >= 4 ? 'severity-high' : '';
            html += `<tr class="${rowClass}"><td>${l.level}</td><td>${l.name}</td><td>${l.human_impact}</td><td>${l.financial_impact}</td><td>${l.downtime}</td></tr>`;
        }
        html += '</table>';
        const severityTable = document.getElementById('severityTable');
        if (severityTable) severityTable.innerHTML = html;
    } catch (error) {
        console.log("خطا در بارگذاری severity:", error);
    }
}

// ========== Likelihood Levels ==========
async function loadLikelihoodLevels() {
    try {
        const response = await fetch(`${API_BASE}/likelihood-levels`, {
            headers: { 'Authorization': `Basic ${token}` }
        });
        const levels = await response.json();
        
        let html = '<table class="level-table"><thead><tr><th>سطح</th><th>نام</th><th>فرکانس</th><th>توضیح</th></tr></thead><tbody>';
        for (const l of levels) {
            let rowClass = l.level >= 4 ? 'likelihood-high' : '';
            html += `<tr class="${rowClass}"><td>${l.level}</td><td>${l.name}</td><td>${l.frequency}</td><td>${l.description}</td></tr>`;
        }
        html += '</tbody></table>';
        const container = document.getElementById('likelihoodTable');
        if (container) container.innerHTML = html;
    } catch (error) {
        console.log("خطا در بارگذاری likelihood:", error);
        const container = document.getElementById('likelihoodTable');
        if (container) container.innerHTML = '<div>خطا در بارگذاری</div>';
    }
}
// ========== آستانه بحرانی سناریوها ==========
async function loadScenarioThresholds() {
    try {
        const response = await fetch(`${API_BASE}/scenario-thresholds`, {
            headers: { 'Authorization': `Basic ${token}` }
        });
        const thresholds = await response.json();
        
        let html = '<table class="threshold-table"><thead><tr><th>سناریو</th><th>آستانه بحرانی (امتیاز)</th><th>اقدامات کنترلی</th></tr></thead><tbody>';
        for (const t of thresholds) {
            html += `<tr class="threshold-critical"><td>⚠️ ${t.scenario_name}</td><td>≥ ${t.critical_threshold}</td><td>${t.action_required}</td></tr>`;
        }
        html += '</tbody></table>';
        const container = document.getElementById('scenarioThresholdsTable');
        if (container) container.innerHTML = html || '<div>هیچ آستانه بحرانی تعریف نشده</div>';
    } catch (error) {
        console.log("خطا در بارگذاری آستانه سناریوها:", error);
        const container = document.getElementById('scenarioThresholdsTable');
        if (container) container.innerHTML = '<div>خطا در بارگذاری</div>';
    }
}

// ========== افکت اسکرول هدر ==========
window.addEventListener('scroll', function() {
    const header = document.querySelector('.header-bg');
    if (header) {
        if (window.scrollY > 50) {
            header.classList.add('scrolled');
        } else {
            header.classList.remove('scrolled');
        }
    }
});

// استایل‌های داینامیک
const styleTag = document.createElement('style');
styleTag.textContent = `
    .risk-high-text { color: #c62828; font-weight: bold; }
    .risk-medium-text { color: #f57f17; font-weight: bold; }
    .risk-low-text { color: #2e7d32; font-weight: bold; }
`;
document.head.appendChild(styleTag);