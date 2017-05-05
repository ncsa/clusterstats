function organize(res) {
	var rows = [];
	$.each(res, function(k, v) {
		rows.push({
			name: v.name,
			replicas: v.replicas,
			cores: v.cores,
			memory: v.memory,
			disk: v.disk.data,
			id: k
		});
	});
    return rows;
}

function replicaSorter(a, b) {
    if (a.running > b.running) return +1;
    if (b.running > a.running) return -1;
    if (a.requested > b.requested) return +1;
    if (b.requested > a.requested) return -1;
    return 0;
}

function replicaFormatter(x, row) {
    result = x.running + '/' + x.requested + ' ';
    if (x.requested < 10) {
        result += '<a href="#" onclick="scale(\'' + row.id + '\', ' + (x.requested+1) + ')">' +
                  '<span class="glyphicon glyphicon-arrow-up" aria-hidden="true" title="scale up"></span>' +
                  '</a> '
    }
    if (x.requested > 0) {
        result += '<a href="#" onclick="scale(\'' + row.id + '\', ' + (x.requested-1) + ')">' +
                  '<span class="glyphicon glyphicon-arrow-down" aria-hidden="true" title="scale up"></span>' +
                  '</a>';
    }
    return result;
}

function floatFormatter(x) {
	return d3.format(".2f")(x);
}

function byteFormatter(x) {
	return d3.format(".2s")(x);
}

function diskFormatter(x) {
    return x;
}

function actionFormatter(id) {
	return '<a href="services/' + id + '/logs">' +
           '<span class="glyphicon glyphicon-list-alt" aria-hidden="true" title="show logs"></span>' +
           '</a> ' +
           '<a href="#" onclick="serviceRestart(\'' + id + '\')">' +
           '<span class="glyphicon glyphicon-refresh" aria-hidden="true" title="restart service"></span>' +
           '</a> ' +
           '<a href="#" onclick="serviceReload(\'' + id + '\')">' +
           '<span class="glyphicon glyphicon-import" aria-hidden="true" title="download latests"></span>' +
           // '</a> ' +
           // '<a href="#" onclick="serviceDestroy(\'' + id + '\')">' +
           // '<span class="glyphicon glyphicon-trash" aria-hidden="true" title="destroy service"></span>' +
    '</a>';
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
    $("#services").bootstrapTable('refresh');
    setTimeout(refresh, 60 * 1000);
}

setTimeout(refresh,  60 * 1000);
