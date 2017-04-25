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

function replicaFormatter(x, row) {
    result = x + ' ';
    if (x < 10) {
        result += '<a href="#" onclick="scale(\'' + row.id + '\', ' + (x+1) + ')">' +
                  '<span class="glyphicon glyphicon-arrow-up" aria-hidden="true" title="scale up"></span>' +
                  '</a> '
    }
    if (x > 0) {
        result += '<a href="#" onclick="scale(\'' + row.id + '\', ' + (x-1) + ')">' +
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
    console.log(x);
    return x;
}

function actionFormatter(id) {
	return '<a href="services/' + id + '/logs">' +
           '<span class="glyphicon glyphicon-list-alt" aria-hidden="true" title="show logs"></span>' +
           // '</a> ' +
           // '<a href="#" onclick="serviceReload(\'' + id + '\')">' +
           // '<span class="glyphicon glyphicon-import" aria-hidden="true" title="download latests"></span>' +
           '</a> ' +
           '<a href="#" onclick="serviceRestart(\'' + id + '\')">' +
           '<span class="glyphicon glyphicon-refresh" aria-hidden="true" title="restart service"></span>' +
           // '</a> ' +
           // '<a href="#" onclick="serviceDestroy(\'' + id + '\')">' +
           // '<span class="glyphicon glyphicon-trash" aria-hidden="true" title="destroy service"></span>' +
           '</a>';
}

function scale(id, replicas) {
    var row = $("#services").bootstrapTable('getRowByUniqueId', id);

    $.ajax({
        type: "PUT",
        url: "api/services/" + row.id + "/scale/" + replicas,
        success: function(data) {
            row['replicas'] = replicas;
            $("#services").bootstrapTable('updateByUniqueId', {id: id, row: row});
        }
    });
}

function serviceRestart(id) {
    var row = $("#services").bootstrapTable('getRowByUniqueId', id),
        old = row['replicas'];

    $.ajax({
        type: "PUT",
        url: "api/services/" + row.id + "/scale/" + 0,
        success: function(data) {
            row['replicas'] = 0;
            $("#services").bootstrapTable('updateByUniqueId', {id: id, row: row});
            setTimeout(scale, 2 * 1000, id, old);
        }
    });
}

function serviceReload(x) {
    console.log("RELOAD  : " + x);
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
