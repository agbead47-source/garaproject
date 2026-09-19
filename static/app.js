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
   * 분석 결과 화면: 행 클릭 → 원문 형광펜 하이라이트
   * --------------------------------------------------------------------- */
  function initHighlight() {
    var sourceBox = document.getElementById('source-box');
    var rows = document.querySelectorAll('.item-row');
    if (!sourceBox || !rows.length) { return; }

    var originalText = sourceBox.textContent;

    function clearHighlight() {
      sourceBox.textContent = originalText;
      document.querySelectorAll('.item-row.selected').forEach(function (r) {
        r.classList.remove('selected');
      });
    }

    function highlight(row) {
      var sentence = row.dataset.source || '';
      var start = sentence ? originalText.indexOf(sentence) : -1;

      if (start === -1) {
        // 원문에서 문장을 찾지 못하면 강조 없이 선택 표시만 한다
        sourceBox.textContent = originalText;
        return;
      }

      var end = start + sentence.length;
      sourceBox.innerHTML =
        escapeHtml(originalText.slice(0, start)) +
        '<mark class="hl" id="hl-target">' + escapeHtml(sentence) + '</mark>' +
        escapeHtml(originalText.slice(end));

      var target = document.getElementById('hl-target');
      if (target) {
        // 스크롤 박스 안에서만 위치를 맞춘다 (페이지 전체는 움직이지 않음)
        sourceBox.scrollTop = target.offsetTop - sourceBox.offsetTop - 60;
      }
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
  });
})();
