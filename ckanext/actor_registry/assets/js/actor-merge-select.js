(function () {
  'use strict';

  function start() {
    var root = document.querySelector('[data-actor-merge-root]');
    if (!root) return;
    var checkboxes = root.querySelectorAll('[data-actor-merge-checkbox]');
    var button = root.querySelector('[data-actor-merge-submit]');
    if (!button) return;

    function update() {
      var checked = Array.prototype.filter.call(checkboxes, function (cb) {
        return cb.checked;
      });
      button.disabled = checked.length !== 2;
      button.dataset.ids = checked.map(function (cb) { return cb.value; }).join(',');
    }

    Array.prototype.forEach.call(checkboxes, function (cb) {
      cb.addEventListener('change', update);
    });

    button.addEventListener('click', function (event) {
      event.preventDefault();
      if (button.disabled) return;
      window.location.href = button.dataset.baseUrl + '?ids=' + encodeURIComponent(button.dataset.ids);
    });

    update();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
})();
