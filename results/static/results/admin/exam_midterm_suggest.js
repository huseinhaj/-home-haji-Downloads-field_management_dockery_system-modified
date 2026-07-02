document.addEventListener('DOMContentLoaded', function () {
  var dateInput = document.getElementById('id_date');
  var examTypeSelect = document.getElementById('id_exam_type');
  if (!dateInput || !examTypeSelect) return;

  var userTouchedType = false;
  examTypeSelect.addEventListener('change', function () {
    userTouchedType = true;
  });

  dateInput.addEventListener('change', function () {
    // Only suggest if the exam_type hasn't been explicitly changed by the user.
    if (userTouchedType || examTypeSelect.value !== 'TERMINAL') return;
    var parts = (dateInput.value || '').split('-'); // yyyy-mm-dd
    var month = parseInt(parts[1], 10);
    if (month === 3 || month === 9) {
      examTypeSelect.value = 'MIDTERM';
    }
  });
});
