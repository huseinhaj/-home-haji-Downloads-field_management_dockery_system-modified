(function () {
    'use strict';

    function buildRegionMap() {
        // Build a map of region_id -> [district options] from the API
        var regionSelect = document.getElementById('id_region');
        var districtSelect = document.getElementById('id_district');
        if (!regionSelect || !districtSelect) return;

        var currentDistrict = districtSelect.value;

        function filterDistricts() {
            var regionId = regionSelect.value;
            if (!regionId) {
                districtSelect.innerHTML = '<option value="">---------</option>';
                return;
            }
            fetch('/api/districts-by-region/?region_id=' + regionId)
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    districtSelect.innerHTML = '<option value="">---------</option>';
                    data.forEach(function (d) {
                        var opt = document.createElement('option');
                        opt.value = d.id;
                        opt.textContent = d.name;
                        if (String(d.id) === String(currentDistrict)) {
                            opt.selected = true;
                        }
                        districtSelect.appendChild(opt);
                    });
                })
                .catch(function () {});
        }

        regionSelect.addEventListener('change', function () {
            currentDistrict = '';
            filterDistricts();
        });

        // On page load, if region is already selected, filter districts
        if (regionSelect.value) {
            filterDistricts();
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', buildRegionMap);
    } else {
        buildRegionMap();
    }
})();
