function organize(res) {
	var rows = [];
	$.each(res, function(k, v) {
	    v.cores.pct = v.cores.total > 0 ? v.cores.used / v.cores.total : 0.0;
	    v.memory.pct = v.memory.total > 0 ? v.memory.used / v.memory.total : 0.0;
	    v.disk.pct = v.disk.available > 0 ? v.disk.used / v.disk.available : 0.0;

		rows.push({
			name: v.name,
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

function actionFormatter(id) {
    // return '<a href="services/' + id + '/logs">' +
    //        '<span class="glyphicon glyphicon-list-alt" aria-hidden="true" title="show logs"></span>' +
    //        '</a> ' +
    //        '<a href="#" onclick="serviceRestart(\'' + id + '\')">' +
    //        '<span class="glyphicon glyphicon-refresh" aria-hidden="true" title="restart service"></span>' +
    //        '</a> ' +
    //        '<a href="#" onclick="serviceReload(\'' + id + '\')">' +
    //        '<span class="glyphicon glyphicon-import" aria-hidden="true" title="download latests"></span>' +
    //        // '</a> ' +
    //        // '<a href="#" onclick="serviceDestroy(\'' + id + '\')">' +
    //        // '<span class="glyphicon glyphicon-trash" aria-hidden="true" title="destroy service"></span>' +
    // '</a>';
	return '';
}

function scale(id, replicas) {
    var row = $("#services").bootstrapTable('getRowByUniqueId', id);

    $.notify("Scaling " + row['name'], "info");
    $.ajax({
        type: "PUT",
        url: "api/services/" + row.id + "/scale/" + replicas,
        success: function(data) {
            row['replicas']['requested'] = replicas;
            $("#services").bootstrapTable('updateByUniqueId', {id: id, row: row});
            $.notify(row['name'] + " scaled to " + replicas, "success");
        },
        error: function(jqXHR, textStatus, errorThrown) {
            $.notify(textStatus + " [" + row['name'] + "] : " + errorThrown, "error");
        }
    });
}

function serviceRestart(id) {
    var row = $("#services").bootstrapTable('getRowByUniqueId', id);

    $.notify("Restarting " + row['name'] + " (takes 30 seconds)", "info");
    $.ajax({
        type: "POST",
        url: "api/services/" + row.id + "/restart",
        success: function(data) {
            $.notify(row['name'] + " restarted", "success");
        },
        error: function(jqXHR, textStatus, errorThrown) {
            $.notify(textStatus + " [" + row['name'] + "] : " + errorThrown, "error");
        }
    });
}

function serviceReload(id) {
    var row = $("#services").bootstrapTable('getRowByUniqueId', id);

    $.notify("Downloading latest image for " + row['name'], "info");
    $.ajax({
        type: "POST",
        url: "api/services/" + row.id + "/update",
        success: function(data) {
            $.notify(row['name'] + " downloaded", "success");
        },
        error: function(jqXHR, textStatus, errorThrown) {
            $.notify(textStatus + " [" + row['name'] + "] : " + errorThrown, "error");
        }
    });
}

function serviceLogs(x) {
    console.log("LOGS    : " + x);
}

function serviceDestroy(x) {
    console.log("DESTROY : " + x);
}

function refresh() {
    $("#nodes").bootstrapTable('refresh');
    setTimeout(refresh, 60 * 1000);
}

setTimeout(refresh,  60 * 1000);
