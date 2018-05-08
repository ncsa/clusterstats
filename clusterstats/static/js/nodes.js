function organize(res) {
	var rows = [];
	$.each(res, function(k, v) {
	    v.cores.pct = v.cores.total > 0 ? v.cores.used / v.cores.total : 0.0;
	    v.memory.pct = v.memory.total > 0 ? v.memory.used / v.memory.total : 0.0;
	    v.disk.pct = v.disk.available > 0 ? v.disk.used / v.disk.available : 0.0;

	    if (v.url != null) {
    	    v.ipaddress = v.url.replace(/tcp:\/\/(.*):2375/, '$1');
        } else {
	        v.ipaddress = "N/A"
        }

		rows.push({
			name: v.name,
            ipaddress: v.ipaddress,
			status: v.status,
			services: v.services.length,
			containers: v.containers.length,
			cores: v.cores,
			memory: v.memory,
			disk: v.disk,
			id: k
		});
	});
    return rows;
}

function percentSorter(a, b) {
    if (a.pct > b.pct) return +1;
    if (a.pct < b.pct) return -1;
    return 0;
}

function numberFormatter(x) {
	return d3.format(".0f")(x);
}

function floatFormatter(x) {
	return d3.format(".2f")(x);
}

function byteFormatter(x) {
	return d3.format(".2s")(x);
}

function coresFormatter(x) {
    return d3.format("%")(x.pct) + " (" + d3.format(".2f")(x.used) + " / " +  d3.format(".2f")(x.total) + ")";
}

function memoryFormatter(x) {
    return d3.format("%")(x.pct) + " (" + d3.format(".2s")(x.used) + " / " +  d3.format(".2s")(x.total) + ")";
}

function diskFormatter(x) {
    return  d3.format("%")(x.pct) + " ( (" + d3.format(".2s")(x.data) + " + " + d3.format(".2s")(x.used - x.data) + ") / " +
        d3.format(".2s")(x.available) + ")";
}

function refresh() {
    $("#nodes").bootstrapTable('refresh');
    setTimeout(refresh, 60 * 1000);
}

setTimeout(refresh,  60 * 1000);
