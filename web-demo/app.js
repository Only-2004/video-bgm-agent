const API_BASE = window.location.origin;
let currentAnalysis = null;
let selectedBGM = null;
let videoId = null;

// 内联试听状态
let previewAudio = null;
let currentPreviewIndex = -1;
let previewTimer = null;
const PREVIEW_DURATION = 20;

// BGM 封面图映射（标题 → 图片路径）
const BGM_COVERS = {
    'Across the room': '/bgm-covers/Across the room.jpg',
    'Beauty And A beat': '/bgm-covers/Beauty And A beat.jpg',
    'Hide U': '/bgm-covers/Hide U.jpg',
    'Hold on': '/bgm-covers/Hold on.jpg',
    'Something Just like this': '/bgm-covers/Something Just like this.jpg',
    'The Hills': '/bgm-covers/The Hills.jpg',
    'Way down': '/bgm-covers/Way down.jpg',
    "We don't talk anymore": "/bgm-covers/We don't talk anymore.jpg",
    'lalaland': '/bgm-covers/LaLa land.jpg',
    'ynetanm': '/bgm-covers/ynetanm.jpg',
    '不只是场梦': '/bgm-covers/不只是场梦.jpg',
    '在你的身边': '/bgm-covers/在你的身边.jpg',
    '我怀念的': '/bgm-covers/我怀念的.jpg',
    '红色高跟鞋': '/bgm-covers/红色高跟鞋.jpg',
    '夏天': '/bgm-covers/夏天.jpg',
    '退后': '/bgm-covers/退后.jpg',
    'exile': '/bgm-covers/exile.jpg',
    'Fallen': '/bgm-covers/fallin.jpg',
    'Love Love - Heyson': '/bgm-covers/Love love.jpg',
    '茫—李润琪': '/bgm-covers/茫.jpg',
    '退后—纯音乐': '/bgm-covers/退后.jpg',
    '@乔什纽曼创作的原声': '/bgm-covers/乔什纽曼.jpg',
};

function getCoverUrl(title) {
    return BGM_COVERS[title] || '';
}

// 统一 BGM 推荐数据格式（兼容 Agent 扁平格式和旧嵌套格式）
function normalizeRec(rec) {
    if (rec.bgm) {
        // 旧嵌套格式: {bgm: {title, artist, ...}, start_sec, climax_hint}
        return {
            title: rec.bgm.title,
            artist: rec.bgm.artist || '',
            score: rec.match_score || 0,
            reason: rec.reason || '',
            start_sec: rec.start_sec || 0,
            preview_url: rec.bgm.preview_url || '',
            climax_hint: rec.climax_hint || '',
        };
    }
    // Agent 扁平格式: {title, artist, score, reason, recommended_start_sec, preview_url}
    return {
        title: rec.title,
        artist: rec.artist || '',
        score: rec.score || rec.fine_score || 0,
        reason: rec.reason || '',
        start_sec: rec.recommended_start_sec || 0,
        preview_url: rec.preview_url || '',
        climax_hint: rec.climax_hint || '',
    };
}

// ---- 内联 BGM 试听 ----
function togglePreview(event, index) {
    event.stopPropagation();
    var recs = window.bgmRecommendations || [];
    if (index >= recs.length) return;
    var rec = normalizeRec(recs[index]);
    if (!rec.preview_url) return;

    // 点击同一卡片且正在播放 → 停止
    if (currentPreviewIndex === index && previewAudio && !previewAudio.paused) {
        stopPreview();
        return;
    }

    // 停止当前播放
    stopPreview();

    // 创建或复用 audio 元素
    if (!previewAudio) previewAudio = new Audio();
    previewAudio.src = rec.preview_url;
    previewAudio.currentTime = rec.start_sec || 0;
    previewAudio.volume = 0.7;

    // 显示进度条
    var progressEl = document.getElementById('preview-progress-' + index);
    var barEl = document.getElementById('preview-bar-' + index);
    if (progressEl) progressEl.style.display = 'flex';
    if (barEl) barEl.style.width = '0%';

    updatePreviewBtnIcon(index, true);

    previewAudio.play().catch(function(err) {
        console.warn('试听播放失败:', err);
        updatePreviewBtnIcon(index, false);
    });

    currentPreviewIndex = index;

    // 定时更新进度 + 20秒自动停止
    previewTimer = setInterval(function() {
        if (previewAudio && !previewAudio.paused) {
            var elapsed = previewAudio.currentTime - (rec.start_sec || 0);
            if (barEl) {
                var pct = Math.min(100, (elapsed / PREVIEW_DURATION) * 100);
                barEl.style.width = pct + '%';
            }
            if (elapsed >= PREVIEW_DURATION) stopPreview();
        }
    }, 200);
}

function stopPreview() {
    if (previewAudio) { previewAudio.pause(); previewAudio.src = ''; }
    if (previewTimer) { clearInterval(previewTimer); previewTimer = null; }
    if (currentPreviewIndex >= 0) {
        updatePreviewBtnIcon(currentPreviewIndex, false);
        var progressEl = document.getElementById('preview-progress-' + currentPreviewIndex);
        if (progressEl) progressEl.style.display = 'none';
    }
    currentPreviewIndex = -1;
}

function updatePreviewBtnIcon(index, playing) {
    var btn = document.querySelector('.bgm-play-btn[data-index="' + index + '"]');
    if (!btn) return;
    if (playing) {
        btn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>';
        btn.classList.add('playing');
    } else {
        btn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>';
        btn.classList.remove('playing');
    }
}

// ---- Page Navigation (GSAP) ----
function showPage(pageId) {
    const oldPage = document.querySelector('.page.active');
    const newPage = document.getElementById(pageId);
    if (!newPage || oldPage === newPage) return;

    // 底部导航高亮
    document.querySelectorAll('.bottom-nav-item').forEach(item => {
        item.classList.toggle('active', item.dataset.nav === pageId);
    });

    // feed 页隐藏底部导航
    const bottomNav = document.getElementById('bottom-nav');
    if (bottomNav) {
        bottomNav.style.display = pageId === 'page-feed' ? 'none' : 'flex';
    }

    // feed 页隐藏AI浮动按钮
    const aiFab = document.getElementById('ai-fab');
    const aiHint = document.getElementById('ai-fab-hint');
    if (aiFab) aiFab.style.display = pageId === 'page-feed' ? 'flex' : 'none';
    if (aiHint) aiHint.style.display = pageId === 'page-feed' ? 'block' : 'none';

    if (typeof gsap !== 'undefined' && oldPage) {
        gsap.to(oldPage, {
            opacity: 0,
            y: -20,
            duration: 0.25,
            ease: 'power2.in',
            onComplete: () => {
                oldPage.classList.remove('active');
                gsap.set(newPage, { opacity: 0, y: 30 });
                newPage.classList.add('active');
                gsap.to(newPage, {
                    opacity: 1,
                    y: 0,
                    duration: 0.45,
                    ease: 'power2.out',
                });
            }
        });
    } else {
        if (oldPage) oldPage.classList.remove('active');
        newPage.classList.add('active');
    }
}

// ---- Video Selection ----
function selectVideo() {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'video/mp4,video/quicktime,.mp4,.mov';
    input.onchange = (e) => {
        const file = e.target.files[0];
        if (file) {
            const video = document.getElementById('preview-video');
            video.src = URL.createObjectURL(file);
            document.getElementById('video-preview').classList.add('show');
            document.getElementById('upload-prompt').classList.add('hidden');
            document.getElementById('upload-area').classList.add('has-video');
            document.getElementById('upload-area').onclick = null;
            document.getElementById('btn-analyze').disabled = false;
            window.selectedFile = file;
        }
    };
    input.click();
}

// ---- Analysis Flow ----
async function startAnalysis() {
    const file = window.selectedFile;
    if (!file) return;

    showPage('page-progress');

    try {
        // Step 1: Upload video
        updateProgress(10, '正在上传视频...');
        const formData = new FormData();
        formData.append('video', file);

        const uploadResp = await fetch(`${API_BASE}/api/upload`, {
            method: 'POST',
            body: formData
        });

        if (!uploadResp.ok) {
            const errData = await uploadResp.json().catch(() => ({}));
            throw new Error(errData.detail || '上传失败');
        }

        const uploadData = await uploadResp.json();
        videoId = uploadData.video_id;

        // Step 2: Start analysis
        updateProgress(20, '正在提取关键帧...');
        const analyzeResp = await fetch(`${API_BASE}/api/analyze`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                video_id: videoId,
                file_path: uploadData.file_path || `uploads/${videoId}${file.name.includes('.') ? '.' + file.name.split('.').pop() : '.mp4'}`
            })
        });

        if (!analyzeResp.ok) {
            const errData = await analyzeResp.json().catch(() => ({}));
            throw new Error(errData.detail || '分析启动失败');
        }

        const analyzeData = await analyzeResp.json();
        const analysisId = analyzeData.analysis_id;

        // Step 3: Poll status
        await pollAnalysisStatus(analysisId);

    } catch (err) {
        alert('分析失败: ' + err.message);
        showPage('page-upload');
    }
}

// ---- Status Polling ----
async function pollAnalysisStatus(analysisId) {
    const MAX_ATTEMPTS = 60;
    let completed = false;
    let attempts = 0;

    while (!completed) {
        if (attempts >= MAX_ATTEMPTS) {
            alert('轮询超时，请刷新页面重试');
            showPage('page-upload');
            return;
        }
        attempts++;

        await sleep(800);

        try {
            const resp = await fetch(`${API_BASE}/api/status/${analysisId}`);
            if (!resp.ok) throw new Error('状态查询失败');

            const data = await resp.json();
            const percent = Math.round(data.progress * 100);
            updateProgress(percent, getStatusText(data.status));

            if (data.status === 'completed') {
                currentAnalysis = data.result;
                window.currentAnalysisId = analysisId;
                completed = true;
                await showResults();
            } else if (data.status === 'failed') {
                alert('分析失败: ' + (data.error || '未知错误'));
                showPage('page-upload');
                completed = true;
            }
        } catch (err) {
            console.warn('状态轮询出错，重试中...', err);
        }
    }
}

function getStatusText(status) {
    const texts = {
        'pending': '等待分析...',
        'analyzing': 'AI 正在感知画面...',
        'completed': '分析完成！',
        'failed': '分析失败'
    };
    return texts[status] || '处理中...';
}

function updateProgress(percent, text) {
    // 环形进度条
    const circumference = 2 * Math.PI * 52; // r=52
    const offset = circumference - (percent / 100) * circumference;
    const ring = document.getElementById('progress-ring-fill');
    if (ring) {
        ring.style.strokeDashoffset = offset;
    }

    const pctEl = document.getElementById('progress-percent');
    if (pctEl) {
        if (typeof gsap !== 'undefined') {
            gsap.to({ val: parseInt(pctEl.textContent) || 0 }, {
                val: percent,
                duration: 0.4,
                ease: 'power2.out',
                onUpdate: function() {
                    pctEl.textContent = Math.round(this.targets()[0].val) + '%';
                }
            });
        } else {
            pctEl.textContent = percent + '%';
        }
    }

    const textEl = document.getElementById('progress-text');
    if (textEl) textEl.textContent = text;
}

// ---- Results ----
async function showResults() {
    showPage('page-result');
    // 等待页面切换动画完成
    await new Promise(r => setTimeout(r, 350));

    try {
        const mimoErrors = currentAnalysis.mimo_errors || [];
        if (mimoErrors.length > 0) {
            const errBanner = document.createElement('div');
            errBanner.style.cssText = 'background:rgba(212,145,154,0.12);color:#a06070;padding:10px 16px;border-radius:12px;margin-bottom:12px;font-size:13px;border:1px solid rgba(212,145,154,0.3);';
            errBanner.innerHTML = `AI 分析部分失败（${mimoErrors.join(', ')}），以下数据为默认值，可能不准确`;
            document.getElementById('scene-info').parentNode.insertBefore(errBanner, document.getElementById('scene-info'));
        }

        // Scene info
        const visual = currentAnalysis.visual || {};
        document.getElementById('scene-info').innerHTML = `
            <div class="scene-badge">${visual.scene || '未知场景'}</div>
            <div class="scene-detail">活动: ${visual.activity || '--'}</div>
            <div class="scene-detail">色调: ${visual.color_tone || '--'}</div>
            <div class="scene-detail">风格: ${visual.visual_style || '--'}</div>
        `;

        // AI analysis description
        const semantic = currentAnalysis.semantic || {};
        let descHtml = '';

        if (semantic.video_description) {
            descHtml += `<div class="desc-section"><div class="desc-label">视频内容</div><div class="desc-text">${semantic.video_description}</div></div>`;
        }

        const oa = semantic.overall_atmosphere || {};
        if (oa.primary_mood || oa.description) {
            let oaText = '';
            if (oa.primary_mood) oaText += `<b>${oa.primary_mood}</b>`;
            if (oa.secondary_mood) oaText += ` · ${oa.secondary_mood}`;
            if (oa.description) oaText += `<br>${oa.description}`;
            descHtml += `<div class="desc-section"><div class="desc-label">整体氛围</div><div class="desc-text">${oaText}</div></div>`;
        }

        if (semantic.emotion_journey) {
            descHtml += `<div class="desc-section"><div class="desc-label">情绪旅程</div><div class="desc-text">${semantic.emotion_journey}</div></div>`;
        }

        const sceneDescs = semantic.scene_descriptions || [];
        if (sceneDescs.length > 0) {
            const sceneHtml = sceneDescs.map(s => {
                const ts = s.timestamp != null ? `${s.timestamp.toFixed(1)}s` : '';
                return `<span style="color:var(--text-muted);">${ts}</span> ${s.description}`;
            }).join('<br>');
            descHtml += `<div class="desc-section"><div class="desc-label">逐场景描述</div><div class="desc-text">${sceneHtml}</div></div>`;
        }

        // 标签
        let metaItems = [];
        if (semantic.video_genre && semantic.video_genre !== '') metaItems.push(semantic.video_genre);
        const rp = semantic.rhythm_pattern || {};
        if (rp.pattern && rp.pattern !== '未知') metaItems.push('剪辑' + rp.pattern);
        if (semantic.theme && semantic.theme !== '未知') metaItems.push(semantic.theme);
        if (semantic.purpose && semantic.purpose !== '未知') metaItems.push(semantic.purpose);
        const sceneAnalysis = semantic.scene_analysis || {};
        if (sceneAnalysis.mood) metaItems.push(sceneAnalysis.mood);
        if (semantic.alignment_strategy) metaItems.push(semantic.alignment_strategy);
        if (semantic.camera_motion_type) metaItems.push(semantic.camera_motion_type);
        const arc = semantic.narrative_arc || {};
        if (arc.arc_type && arc.arc_type !== '未知') metaItems.push('弧线:' + arc.arc_type);
        if (metaItems.length) {
            descHtml += `<div class="desc-section"><div class="desc-tags">${metaItems.map(t => `<span class="desc-tag">${t}</span>`).join('')}</div></div>`;
        }

        document.getElementById('ai-description').innerHTML = descHtml || '<span style="color:var(--text-muted);font-size:13px;">暂无分析数据</span>';
    } catch (err) {
        console.error('Error rendering analysis results:', err);
        document.getElementById('scene-info').innerHTML =
            '<div style="color:#c0392b;">结果数据解析失败</div>';
    }

    // BGM recommendations
    document.getElementById('bgm-list').innerHTML =
        '<div style="text-align:center;padding:20px;color:var(--text-muted);">正在加载推荐...</div>';

    try {
        const matchResp = await fetch(`${API_BASE}/api/match`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ analysis_id: window.currentAnalysisId })
        });

        if (!matchResp.ok) {
            const errData = await matchResp.json().catch(() => ({}));
            throw new Error(errData.detail || `匹配失败 (HTTP ${matchResp.status})`);
        }

        const matchData = await matchResp.json();
        console.log('[match] API 返回:', JSON.stringify(matchData).substring(0, 500));
        const bgmList = matchData.recommendations || [];
        console.log('[match] bgmList 长度:', bgmList.length);

        if (bgmList.length === 0) {
            document.getElementById('bgm-list').innerHTML =
                '<div style="text-align:center;padding:20px;color:var(--text-muted);">暂无推荐 BGM</div>';
            return;
        }

        renderBGMList(bgmList);
        window.bgmRecommendations = bgmList;
        try { showResultActions(); } catch(e) { console.error('[debug] showResultActions error:', e); }
    } catch (err) {
        console.error('[match] 错误:', err);
        document.getElementById('bgm-list').innerHTML =
            `<div style="text-align:center;padding:20px;color:#c0392b;">加载失败: ${err.message}<br><small>${err.stack || ''}</small></div>`;
    }
}

function renderBGMList(bgmList) {
    const container = document.getElementById('bgm-list');

    const cardsHtml = bgmList.map(normalizeRec).map((rec, i) => {
        const coverUrl = getCoverUrl(rec.title);

        let hintHtml = '';
        if (rec.start_sec > 0) {
            const min = Math.floor(rec.start_sec / 60);
            const sec = Math.floor(rec.start_sec % 60);
            const timeStr = min > 0 ? `${min}分${sec}秒` : `${sec}秒`;
            hintHtml += `<div class="bgm-hint">&#9654; 推荐从 ${timeStr} 开始</div>`;
        }
        if (rec.climax_hint) {
            hintHtml += `<div class="bgm-hint climax">&#9733; ${rec.climax_hint}</div>`;
        }

        const coverHtml = coverUrl
            ? `<img src="${coverUrl}" alt="${rec.title}" loading="lazy">`
            : `<div style="width:100%;height:180px;background:linear-gradient(135deg,#e8b8be,#c4dce8);"></div>`;

        return `
        <div class="carousel-card" data-index="${i}">
            <div class="card-cover">
                ${coverHtml}
                <button class="bgm-play-btn" data-index="${i}" onclick="togglePreview(event, ${i})">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                </button>
            </div>
            <div class="card-body">
                <div class="card-title">${rec.title}</div>
                ${rec.artist ? `<div class="card-artist">${rec.artist}</div>` : ''}
                <div class="preview-progress" id="preview-progress-${i}" style="display:none;">
                    <div class="preview-progress-bar" id="preview-bar-${i}"></div>
                </div>
                ${hintHtml}
            </div>
        </div>`;
    }).join('');

    container.innerHTML = `
        <div class="carousel-scene" id="carousel-scene">
            <div class="carousel-track" id="carousel-track">
                ${cardsHtml}
            </div>
        </div>
        <div class="carousel-dots" id="carousel-dots"></div>
    `;

    initCarousel(bgmList.length);

    // GSAP 入场
    if (typeof gsap !== 'undefined') {
        gsap.from('#page-result .analysis-card', {
            opacity: 0, y: 24, stagger: 0.12, duration: 0.5, ease: 'power2.out'
        });
    }
}

// ---- 3D 卡片堆叠轮播 ----
function initCarousel(total) {
    const scene = document.getElementById('carousel-scene');
    const track = document.getElementById('carousel-track');
    const cards = Array.from(track.querySelectorAll('.carousel-card'));
    if (cards.length === 0) return;

    let currentIndex = 0;
    let isDragging = false;
    let startX = 0;
    let dragDelta = 0;
    let autoTimer = null;

    const maxIndex = total - 1;

    // 生成指示点
    const dotsContainer = document.getElementById('carousel-dots');
    dotsContainer.innerHTML = cards.map((_, i) =>
        `<div class="carousel-dot ${i === 0 ? 'active' : ''}" data-i="${i}"></div>`
    ).join('');

    // 根据屏幕宽度调整参数
    function getCardWidth() {
        return window.innerWidth <= 768 ? 220 : 260;
    }

    // 3D 定位每张卡片
    function layoutCards(animate = true) {
        const cw = getCardWidth();

        cards.forEach((card, i) => {
            const offset = i - currentIndex;
            const absOffset = Math.abs(offset);

            // 超出视野的卡片隐藏
            if (absOffset > 2) {
                card.style.opacity = '0';
                card.style.pointerEvents = 'none';
                card.style.visibility = 'hidden';
                return;
            }

            card.style.visibility = 'visible';
            card.style.pointerEvents = absOffset === 0 ? 'auto' : 'auto';

            const scale = absOffset === 0 ? 1 : absOffset === 1 ? 0.82 : 0.65;
            const tx = offset * (cw * 0.38);
            const ty = absOffset * 18;
            const opacity = absOffset === 0 ? 1 : absOffset === 1 ? 0.55 : 0.2;
            const blur = absOffset === 0 ? 0 : absOffset === 1 ? 2 : 4;
            const zIndex = 10 - absOffset;

            if (animate) {
                card.style.transition = 'transform 0.5s cubic-bezier(0.25, 1, 0.5, 1), opacity 0.5s ease, filter 0.5s ease, box-shadow 0.5s ease';
            } else {
                card.style.transition = 'none';
            }

            card.style.transform = `translateX(${tx}px) translateY(${ty}px) scale(${scale})`;
            card.style.opacity = opacity;
            card.style.filter = blur > 0 ? `blur(${blur}px)` : 'none';
            card.style.zIndex = zIndex;
            card.classList.toggle('active', absOffset === 0);
        });

        // 更新指示点
        dotsContainer.querySelectorAll('.carousel-dot').forEach((d, i) => {
            d.classList.toggle('active', i === currentIndex);
        });
    }

    function goTo(index) {
        currentIndex = Math.max(0, Math.min(maxIndex, index));
        layoutCards(true);
    }

    // 点击侧边卡片 → 滑到中心；点击中心卡片 → 选择
    track.addEventListener('click', e => {
        const card = e.target.closest('.carousel-card');
        if (!card) return;
        const idx = parseInt(card.dataset.index);
        if (idx === currentIndex) {
            selectBGM(idx);
        } else {
            goTo(idx);
            startAutoPlay();
        }
    });

    // 拖拽控制
    function onPointerDown(e) {
        if (e.button && e.button !== 0) return;
        isDragging = true;
        startX = e.type.includes('touch') ? e.touches[0].clientX : e.clientX;
        dragDelta = 0;
        clearInterval(autoTimer);
        cards.forEach(c => c.style.transition = 'none');
    }

    function onPointerMove(e) {
        if (!isDragging) return;
        const x = e.type.includes('touch') ? e.touches[0].clientX : e.clientX;
        dragDelta = x - startX;
        const cw = getCardWidth();

        cards.forEach((card, i) => {
            const offset = i - currentIndex;
            const absOffset = Math.abs(offset);
            if (absOffset > 2) return;

            const dragOffset = dragDelta / cw * 0.8;
            const tx = offset * (cw * 0.38) + dragOffset * cw * 0.38;
            const ty = absOffset * 18;
            const scale = absOffset === 0 ? 1 : absOffset === 1 ? 0.82 : 0.65;

            card.style.transform = `translateX(${tx}px) translateY(${ty}px) scale(${scale})`;
        });
    }

    function onPointerUp() {
        if (!isDragging) return;
        isDragging = false;

        const threshold = getCardWidth() * 0.2;
        if (dragDelta < -threshold && currentIndex < maxIndex) {
            currentIndex++;
        } else if (dragDelta > threshold && currentIndex > 0) {
            currentIndex--;
        }

        layoutCards(true);
        startAutoPlay();
    }

    scene.addEventListener('touchstart', onPointerDown, { passive: true });
    scene.addEventListener('touchmove', onPointerMove, { passive: true });
    scene.addEventListener('touchend', onPointerUp);
    scene.addEventListener('mousedown', onPointerDown);
    window.addEventListener('mousemove', onPointerMove);
    window.addEventListener('mouseup', onPointerUp);
    scene.addEventListener('dragstart', e => e.preventDefault());

    // 指示点点击
    dotsContainer.addEventListener('click', e => {
        const dot = e.target.closest('.carousel-dot');
        if (!dot) return;
        goTo(parseInt(dot.dataset.i));
        startAutoPlay();
    });

    // 自动轮播
    function startAutoPlay() {
        clearInterval(autoTimer);
        autoTimer = setInterval(() => {
            currentIndex = currentIndex >= maxIndex ? 0 : currentIndex + 1;
            layoutCards(true);
        }, 4500);
    }
    startAutoPlay();

    // 初始定位
    layoutCards(false);
}

// ---- BGM Selection ----
function selectBGM(index) {
    stopPreview();
    document.querySelectorAll('.carousel-card').forEach(c => c.classList.remove('selected'));
    const card = document.querySelector(`.carousel-card[data-index="${index}"]`);
    if (card) card.classList.add('selected');
    selectedBGM = normalizeRec(window.bgmRecommendations[index]);

    showPage('page-preview');

    const bgm = selectedBGM;
    document.getElementById('preview-bgm-info').innerHTML = `
        <div class="bgm-title">${bgm.title}</div>
        ${bgm.artist ? `<div class="bgm-artist">${bgm.artist}</div>` : ''}
    `;

    const mainVideo = document.getElementById('main-video');
    if (window.selectedFile) {
        mainVideo.src = URL.createObjectURL(window.selectedFile);
        mainVideo.muted = true;
        mainVideo.play().catch(() => {});
    }

    const bgmAudio = document.getElementById('bgm-audio');
    if (bgm.preview_url && bgm.preview_url.startsWith('/')) {
        bgmAudio.src = bgm.preview_url;
    } else {
        bgmAudio.src = '';
    }
    bgmAudio.volume = document.getElementById('volume-slider').value / 100;
    if (selectedBGM.start_sec > 0) {
        bgmAudio.currentTime = selectedBGM.start_sec;
    }
    bgmAudio.play().catch(() => {});
}

// ---- Preview Controls ----
function switchBGM() {
    const bgmAudio = document.getElementById('bgm-audio');
    const mainVideo = document.getElementById('main-video');
    if (bgmAudio) { bgmAudio.pause(); bgmAudio.src = ''; }
    if (mainVideo) { mainVideo.pause(); }
    showPage('page-result');
}

function confirmSelection() {
    const volume = document.getElementById('volume-slider').value;
    alert(`已选择: ${selectedBGM.title}\nBGM 音量: ${volume}%`);
}

// Volume slider
document.addEventListener('DOMContentLoaded', () => {
    const slider = document.getElementById('volume-slider');
    const display = document.getElementById('volume-value');
    if (slider && display) {
        slider.addEventListener('input', () => {
            display.textContent = `${slider.value}%`;
            const bgmAudio = document.getElementById('bgm-audio');
            if (bgmAudio) bgmAudio.volume = slider.value / 100;
        });
    }
});

// ---- Utility ----
function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

// ---- 结果页操作按钮 ----
function showResultActions() {
    console.log('[debug] showResultActions called');
    const el = document.getElementById('result-actions');
    console.log('[debug] result-actions element:', el);
    if (el) {
        el.style.display = 'flex';
        console.log('[debug] display set to flex');
        if (typeof gsap !== 'undefined') {
            gsap.from(el.querySelectorAll('.btn-action'), {
                opacity: 0, y: 16, stagger: 0.1, duration: 0.4, ease: 'power2.out', delay: 0.3
            });
        }
    }
}

function handlePublish() {
    alert('发布成功！你的配乐作品已提交审核。');
}

function handleShare() {
    const url = window.location.href;
    if (navigator.share) {
        navigator.share({ title: '画境生音 — AI 视频配乐', url });
    } else if (navigator.clipboard) {
        navigator.clipboard.writeText(url).then(() => {
            alert('链接已复制到剪贴板');
        });
    } else {
        alert('分享链接: ' + url);
    }
}

function handleRegenerate() {
    if (window.currentAnalysisId) {
        showPage('page-result');
        // 显示加载状态
        document.getElementById('bgm-list').innerHTML =
            '<div style="text-align:center;padding:20px;color:var(--text-muted);">正在重新生成推荐...</div>';
        document.getElementById('result-actions').style.display = 'none';

        // 重新请求匹配
        fetch(`${API_BASE}/api/match`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ analysis_id: window.currentAnalysisId })
        })
        .then(r => r.json())
        .then(data => {
            const bgmList = data.recommendations || [];
            if (bgmList.length === 0) {
                document.getElementById('bgm-list').innerHTML =
                    '<div style="text-align:center;padding:20px;color:var(--text-muted);">暂无推荐 BGM</div>';
                return;
            }
            window.bgmRecommendations = bgmList;
            renderBGMList(bgmList);
            showResultActions();
        })
        .catch(err => {
            document.getElementById('bgm-list').innerHTML =
                `<div style="text-align:center;padding:20px;color:#c0392b;">重新生成失败: ${err.message}</div>`;
        });
    }
}

// ---- Feed 页面导航 ----
function goToFeed() {
    showPage('page-feed');
    const feedVideo = document.getElementById('feed-video');
    if (feedVideo && feedVideo.src) feedVideo.play().catch(() => {});
}

function goToUpload() {
    showPage('page-upload');
}

// 顶部 tab 和底部 nav 一一对应
const TAB_NAV_MAP = [
    { tab: '发现', nav: 'feed' },
    { tab: '听见', nav: 'video' },
    { tab: '直播', nav: 'upload' },
    { tab: '交友', nav: 'star' },
    { tab: '看见', nav: 'mine' }
];

function switchTab(index) {
    // 更新顶部 tab 高亮
    document.querySelectorAll('.feed-tab').forEach((t, i) => {
        t.classList.toggle('active', i === index);
    });
    // 更新底部 nav 高亮
    const navName = TAB_NAV_MAP[index].nav;
    document.querySelectorAll('.bottom-nav-item').forEach(item => {
        item.classList.toggle('active', item.dataset.nav === navName);
    });
}

function navTo(page) {
    const pageMap = {
        'feed': 'page-feed',
        'video': 'page-feed',
        'upload': 'page-upload',
        'star': 'page-result',
        'mine': 'page-preview'
    };
    // 同步顶部 tab
    const tabIdx = TAB_NAV_MAP.findIndex(t => t.nav === page);
    if (tabIdx >= 0) {
        document.querySelectorAll('.feed-tab').forEach((t, i) => {
            t.classList.toggle('active', i === tabIdx);
        });
    }
    const target = pageMap[page];
    if (target) showPage(target);
}

// ---- 初始化 ----
document.addEventListener('DOMContentLoaded', () => {
    // 自动播放 feed 视频
    const feedVideo = document.getElementById('feed-video');
    if (feedVideo) {
        feedVideo.play().catch(() => {});
    }

    // AI 助手按钮拖拽
    initFabDrag();
});

function initFabDrag() {
    const fab = document.getElementById('ai-fab');
    const hint = document.getElementById('ai-fab-hint');
    if (!fab) return;

    let isDragging = false;
    let startX, startY, startLeft, startTop;
    let hasMoved = false;

    function onPointerDown(e) {
        if (e.button && e.button !== 0) return;
        isDragging = true;
        hasMoved = false;
        const rect = fab.getBoundingClientRect();
        const parentRect = fab.parentElement.getBoundingClientRect();
        startX = e.type.includes('touch') ? e.touches[0].clientX : e.clientX;
        startY = e.type.includes('touch') ? e.touches[0].clientY : e.clientY;
        startLeft = rect.left - parentRect.left;
        startTop = rect.top - parentRect.top;
        fab.style.transition = 'none';
        fab.style.right = 'auto';
        fab.style.bottom = 'auto';
        e.preventDefault();
    }

    function onPointerMove(e) {
        if (!isDragging) return;
        const x = e.type.includes('touch') ? e.touches[0].clientX : e.clientX;
        const y = e.type.includes('touch') ? e.touches[0].clientY : e.clientY;
        const dx = x - startX;
        const dy = y - startY;

        if (Math.abs(dx) > 5 || Math.abs(dy) > 5) hasMoved = true;

        const parentRect = fab.parentElement.getBoundingClientRect();
        let newLeft = startLeft + dx;
        let newTop = startTop + dy;

        // 边界限制
        newLeft = Math.max(0, Math.min(parentRect.width - fab.offsetWidth, newLeft));
        newTop = Math.max(0, Math.min(parentRect.height - fab.offsetHeight, newTop));

        fab.style.left = newLeft + 'px';
        fab.style.top = newTop + 'px';
    }

    function onPointerUp(e) {
        if (!isDragging) return;
        isDragging = false;
        fab.style.transition = 'transform 0.3s cubic-bezier(0.34, 1.56, 0.64, 1), left 0.3s ease, top 0.3s ease';

        // 如果没有移动，视为点击
        if (!hasMoved) {
            goToUpload();
        }
    }

    fab.addEventListener('mousedown', onPointerDown);
    window.addEventListener('mousemove', onPointerMove);
    window.addEventListener('mouseup', onPointerUp);
    fab.addEventListener('touchstart', onPointerDown, { passive: false });
    fab.addEventListener('touchmove', onPointerMove, { passive: false });
    fab.addEventListener('touchend', onPointerUp);

    // 阻止拖拽时选中文本
    fab.addEventListener('dragstart', e => e.preventDefault());
}

// ======== Agent FC 模式：SSE 流式分析 ========
let agentSessionId = null;

async function startAgentAnalysis() {
    var file = window.selectedFile;
    if (!file) return;
    showPage('page-progress');
    try {
        updateProgress(10, '正在上传视频...');
        var formData = new FormData();
        formData.append('video', file);
        var uploadResp = await fetch(API_BASE + '/api/upload', { method: 'POST', body: formData });
        if (!uploadResp.ok) throw new Error('上传失败');
        var uploadData = await uploadResp.json();
        videoId = uploadData.video_id;
        updateProgress(15, 'AI 助手启动中...');
        var resp = await fetch(API_BASE + '/api/agent/analyze', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ video_id: videoId, file_path: uploadData.file_path })
        });
        if (!resp.ok) throw new Error('Agent 分析启动失败');
        if (!resp.body) throw new Error('无响应流');
        var reader = resp.body.getReader();
        var decoder = new TextDecoder();
        var buffer = '';
        var finalResult = null;
        while (true) {
            var result = await reader.read();
            if (result.done) break;
            buffer += decoder.decode(result.value, { stream: true });
            var lines = buffer.split('\n');
            buffer = lines.pop() || '';
            for (var li = 0; li < lines.length; li++) {
                var line = lines[li];
                if (line.indexOf('data: ') !== 0) continue;
                var jsonStr = line.slice(6).trim();
                if (!jsonStr) continue;
                try {
                    var event = JSON.parse(jsonStr);
                    switch (event.type) {
                        case 'tool_call':
                            updateProgress(25, getAgentToolText(event.tool));
                            break;
                        case 'tool_result':
                            updateProgress(50, getAgentResultText(event.tool));
                            if (event.tool === 'analyze_video' && event.result && event.result.raw_analysis) {
                                currentAnalysis = event.result.raw_analysis;
                            }
                            break;
                        case 'final':
                            finalResult = event;
                            if (event.recommendations && event.recommendations.length > 0) {
                                window.bgmRecommendations = event.recommendations;
                            }
                            updateProgress(100, '分析完成！');
                            await showAgentResults(event);
                            break;
                        case 'error':
                            throw new Error(event.message);
                    }
                } catch (parseErr) {
                    if (String(parseErr.message) !== '分析完成！') {
                        console.warn('解析跳过:', jsonStr ? jsonStr.substring(0, 80) : '');
                    }
                }
            }
        }
        if (!finalResult) throw new Error('Agent 未返回结果');
    } catch (err) {
        alert('分析失败: ' + err.message);
        showPage('page-upload');
    }
}

function getAgentToolText(tool) {
    var texts = {
        'analyze_video': 'AI 正在分析画面内容...',
        'search_bgm': 'AI 正在搜索曲库...',
        'score_and_rank': 'AI 正在精排序候选...',
        'adjust_volume': 'AI 正在调整音量...',
        'detect_conflict': 'AI 正在检测冲突...',
    };
    return texts[tool] || 'AI 正在分析...';
}

function getAgentResultText(tool) {
    var texts = {
        'analyze_video': '画面分析完成',
        'search_bgm': '曲库搜索完成',
        'score_and_rank': '精排序完成',
        'adjust_volume': '音量调整完成',
        'detect_conflict': '冲突检测完成',
    };
    return texts[tool] || '分析完成';
}

async function showAgentResults(event) {
    showPage('page-result');
    await sleep(350);
    var content = event.content || '';
    document.getElementById('ai-description').innerHTML =
        '<div style="font-size:14px;line-height:1.7;color:var(--text);">' + content.replace(/\n/g, '<br>') + '</div>';
    document.getElementById('scene-info').innerHTML =
        '<div style="font-size:13px;color:var(--text-muted);">由 AI 自主分析生成</div>';
    var recs = event.recommendations || [];
    if (recs.length === 0) {
        document.getElementById('bgm-list').innerHTML =
            '<div style="text-align:center;padding:20px;color:var(--text-muted);">暂无推荐 BGM</div>';
        return;
    }
    renderBGMList(recs);
    var actionsEl = document.getElementById('result-actions');
    if (actionsEl) actionsEl.style.display = 'flex';
    var chatBar = document.getElementById('agent-chat-bar');
    if (chatBar) chatBar.style.display = 'flex';
}

async function sendAgentMessage() {
    var input = document.getElementById('agent-chat-input');
    var message = input.value.trim();
    if (!message || !agentSessionId) return;
    input.value = '';
    input.disabled = true;
    addChatMessage('user', message);
    var thinkingEl = addChatMessage('agent', '思考中...');
    try {
        var resp = await fetch(API_BASE + '/api/agent/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: agentSessionId, message: message })
        });
        if (!resp.ok || !resp.body) throw new Error('对话请求失败');
        var reader = resp.body.getReader();
        var decoder = new TextDecoder();
        var buffer = '';
        while (true) {
            var result = await reader.read();
            if (result.done) break;
            buffer += decoder.decode(result.value, { stream: true });
            var lines = buffer.split('\n');
            buffer = lines.pop() || '';
            for (var li = 0; li < lines.length; li++) {
                var line = lines[li];
                if (line.indexOf('data: ') !== 0) continue;
                var jsonStr = line.slice(6).trim();
                if (!jsonStr) continue;
                try {
                    var event = JSON.parse(jsonStr);
                    if (event.type === 'final') {
                        thinkingEl.innerHTML = (event.content || '').replace(/\n/g, '<br>');
                        if (event.recommendations && event.recommendations.length > 0) {
                            window.bgmRecommendations = event.recommendations;
                            renderBGMList(event.recommendations);
                        }
                    }
                } catch (e) {}
            }
        }
    } catch (err) {
        thinkingEl.innerHTML = '错误: ' + err.message;
    }
    input.disabled = false;
    input.focus();
}

function addChatMessage(role, text) {
    var container = document.getElementById('agent-chat-messages');
    var el = document.createElement('div');
    el.className = 'chat-message chat-' + role;
    el.innerHTML = text;
    container.appendChild(el);
    container.scrollTop = container.scrollHeight;
    return el;
}

// Enter 发送
(function() {
    var origListener = document.addEventListener;
    document.addEventListener('DOMContentLoaded', function() {
        var chatInput = document.getElementById('agent-chat-input');
        if (chatInput) {
            chatInput.addEventListener('keydown', function(e) {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    sendAgentMessage();
                }
            });
        }
    });
})();

