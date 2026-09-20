/* To-do Trade - 공통 스크립트 (UI 가안) */

(function () {
  'use strict';

  function escapeHtml(text) {
    return text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  /* -----------------------------------------------------------------------
   * 분석 결과 화면: 행 클릭 → 양식에서 그 줄을 강조
   * -----------------------------------------------------------------------
   * 개발요청서는 대부분 엑셀 양식이라 원문이 줄글이 아니라 표다.
   * 그래서 문장을 찾아 형광펜을 긋던 걸 **줄 번호로 짚는 방식**으로 바꿨다.
   * "6쪽 세 번째 문장" 이 아니라 "6-2 Target Unit Price" 라야 사람이 찾는다.
   * --------------------------------------------------------------------- */
  function initHighlight() {
    var sourceBox = document.getElementById('source-box');
    var rows = document.querySelectorAll('.item-row');
    if (!sourceBox || !rows.length) { return; }

    function clearHighlight() {
      sourceBox.querySelectorAll('.form-row.hl').forEach(function (r) {
        r.classList.remove('hl');
      });
      document.querySelectorAll('.item-row.selected').forEach(function (r) {
        r.classList.remove('selected');
      });
    }

    function highlight(row) {
      var no = row.dataset.row || '';
      if (!no) { return; }                     // 양식에 해당 칸이 없는 항목
      var target = document.getElementById('fr-' + no);
      if (!target) { return; }

      target.classList.add('hl');
      /* 스크롤 박스 안에서만 위치를 맞춘다 (페이지 전체는 움직이지 않음) */
      sourceBox.scrollTop = target.offsetTop - sourceBox.offsetTop - 60;
    }

    rows.forEach(function (row) {
      row.addEventListener('click', function () {
        var alreadySelected = row.classList.contains('selected');
        clearHighlight();
        if (alreadySelected) { return; }
        row.classList.add('selected');
        highlight(row);
      });
    });
  }

  /* -----------------------------------------------------------------------
   * 변환 문서 화면: 값 인라인 수정
   * --------------------------------------------------------------------- */
  /* 고치는 자리는 변환 문서(.doc-text) 하나뿐이다. 분석 결과는 원문에서 읽어낸
     그대로 두고(읽기 전용), 손대는 일은 전달 문서에서 한다. */
  function initInlineEdit() {
    var cells = document.querySelectorAll('.doc-text');
    if (!cells.length) { return; }

    /* 고친 값을 서버에 남긴다. 새로고침해도 남아 있어야 이 화면에서 고치게 된다.
       저장이 실패하면 화면만 고쳐진 채로 두지 않고 원래 값으로 되돌린다. */
    function persist(cell, value, previous, wasEdited) {
      var doc = cell.dataset.doc;
      if (!doc) { return; }                    // 저장 대상이 아닌 화면

      fetch('/api/doc-edit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ doc: doc, field: cell.dataset.field, value: value })
      }).then(function (res) {
        return res.ok ? res.json() : Promise.reject(res.status);
      }).then(function (data) {
        cell.dataset.value = data.value;
        cell.classList.toggle('edited', data.edited);
        render(cell);
        document.dispatchEvent(new CustomEvent('doc-edit-saved'));
      }).catch(function () {
        cell.dataset.value = previous;
        cell.classList.toggle('edited', wasEdited);
        render(cell);
        if (window.showToast) {
          window.showToast('수정을 저장하지 못했습니다. 다시 시도해 주세요.', 'error');
        }
      });
    }

    function render(cell) {
      var value = cell.dataset.value || '';
      var empty = cell.dataset.placeholder || '— 값 없음';
      cell.textContent = value || empty;
      cell.classList.toggle('empty', !value);
    }

    function startEdit(cell) {
      if (cell.querySelector('input')) { return; }

      var current = cell.dataset.value || '';
      var wasEdited = cell.classList.contains('edited');
      var input = document.createElement('input');
      input.type = 'text';
      input.className = 'inline-input';
      input.value = current;

      cell.textContent = '';
      cell.classList.remove('empty');
      cell.appendChild(input);
      input.focus();
      input.select();

      var done = false;

      function finish(save) {
        if (done) { return; }
        done = true;

        var next = save ? input.value.trim() : current;
        cell.dataset.value = next;
        render(cell);

        if (save && next !== current) {
          cell.classList.add('edited');
          persist(cell, next, current, wasEdited);
        }
      }

      input.addEventListener('click', function (e) { e.stopPropagation(); });
      input.addEventListener('blur', function () { finish(true); });
      input.addEventListener('keydown', function (e) {
        if (e.key === 'Enter') { e.preventDefault(); finish(true); }
        if (e.key === 'Escape') { e.preventDefault(); finish(false); }
      });
    }

    cells.forEach(function (cell) {
      if (cell.dataset.placeholder && !cell.dataset.value) { render(cell); }
      cell.addEventListener('click', function (e) {
        // 값 수정 중에는 행 하이라이트가 끼어들지 않게 한다
        e.stopPropagation();
        startEdit(cell);
      });
    });
  }

  /* -----------------------------------------------------------------------
   * 무역 도우미 - 규칙 기반 챗봇 (가안)
   * --------------------------------------------------------------------- */
  /* 대화는 화면에만 남는다. 새로고침하면 사라진다 (가안) */
  function initChat() {
    var fab = document.getElementById('chat-fab');
    var panel = document.getElementById('chat-panel');
    if (!fab || !panel) { return; }

    var log = document.getElementById('chat-log');
    var form = document.getElementById('chat-form');
    var input = document.getElementById('chat-input');
    var send = document.getElementById('chat-send');
    var started = false;

    function scroll() { log.scrollTop = log.scrollHeight; }

    function bubble(side, text) {
      var row = document.createElement('div');
      row.className = 'chat-row ' + side;
      var box = document.createElement('div');
      box.className = 'chat-bubble';
      box.textContent = text;
      row.appendChild(box);
      log.appendChild(row);
      scroll();
      return box;
    }

    function chips(list) {
      if (!list || !list.length) { return; }
      var wrap = document.createElement('div');
      wrap.className = 'chat-chips';
      list.forEach(function (text) {
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'chat-chip';
        btn.textContent = text;
        btn.addEventListener('click', function () { ask(text); });
        wrap.appendChild(btn);
      });
      log.appendChild(wrap);
      scroll();
    }

    function extras(data) {
      if (data.source) {
        var src = document.createElement('div');
        src.className = 'chat-source';
        src.textContent = '출처: ' + data.source;
        log.appendChild(src);
      }
      (data.links || []).forEach(function (link) {
        var a = document.createElement('a');
        a.className = 'chat-link';
        a.href = link.href;
        a.textContent = link.label + ' →';
        log.appendChild(a);
      });
      chips(data.chips);
    }

    function ask(question) {
      if (!question) { return; }
      bubble('me', question);
      input.value = '';
      send.classList.add('is-busy');

      var typing = bubble('bot', '…');

      fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ q: question, project: panel.dataset.project || '' })
      }).then(function (res) {
        return res.ok ? res.json() : Promise.reject(res.status);
      }).then(function (data) {
        typing.textContent = data.text;
        extras(data);
      }).catch(function () {
        // 답을 못 받았으면 못 받았다고 한다. 지어내지 않는다
        typing.textContent = '답을 가져오지 못했습니다. 잠시 뒤 다시 물어봐 주세요.';
        typing.classList.add('chat-failed');
      }).then(function () {
        send.classList.remove('is-busy');
        scroll();
      });
    }

    function open() {
      panel.hidden = false;
      fab.classList.add('on');
      if (!started) {
        started = true;
        bubble('bot', log.dataset.greeting || '무엇을 도와드릴까요?');
        try {
          chips(JSON.parse(log.dataset.chips || '[]'));
        } catch (e) { /* 추천 질문이 없어도 대화는 된다 */ }
      }
      input.focus();
    }

    function close() {
      panel.hidden = true;
      fab.classList.remove('on');
    }

    fab.addEventListener('click', function () {
      if (panel.hidden) { open(); } else { close(); }
    });
    document.getElementById('chat-close').addEventListener('click', close);

    form.addEventListener('submit', function (e) {
      e.preventDefault();
      ask(input.value.trim());
    });

    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && !panel.hidden) { close(); }
    });
  }

  /* -----------------------------------------------------------------------
   * 공통 토스트 메시지
   * --------------------------------------------------------------------- */
  var toastTimer = null;

  function showToast(message, type) {
    var box = document.getElementById('toast');
    if (!box) {
      box = document.createElement('div');
      box.id = 'toast';
      box.className = 'toast';
      document.body.appendChild(box);
    }

    box.textContent = message;
    box.className = 'toast show' + (type ? ' ' + type : '');

    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () {
      box.className = 'toast';
    }, 2400);
  }

  window.showToast = showToast;

  document.addEventListener('DOMContentLoaded', function () {
    initHighlight();
    initInlineEdit();
    initChat();
  });
})();
