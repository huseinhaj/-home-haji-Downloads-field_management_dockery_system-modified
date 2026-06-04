document.addEventListener('DOMContentLoaded', function () {
    const regionSelect = document.getElementById('id_region');
    const districtSelect = document.getElementById('id_district');

    if (!regionSelect || !districtSelect) return;

    regionSelect.addEventListener('change', function () {
        const regionId = this.value;
        districtSelect.innerHTML = '<option value="">---------</option>';

        if (!regionId) return;

        fetch('/api/districts-by-region/?region_id=' + regionId)
            .then(r => r.json())
            .then(data => {
                data.forEach(function (d) {
                    const opt = document.createElement('option');
                    opt.value = d.id;
                    opt.textContent = d.name;
                    districtSelect.appendChild(opt);
                });
            });
    });
});
