
import json

import streamlit.components.v1 as components


def render_live_map(
    depot,
    customers,
    simulation,
    solution,
    current_minute,
    height=550,
):
    """Render a persistent Leaflet map with browser-side vehicle updates."""

    from src.simulation import customer_status, vehicle_position

    customer_data = []

    for _, customer in customers.iterrows():
        customer_id = customer["customer_id"]
        customer_data.append({
            "id": str(customer_id),
            "lat": float(customer["latitude"]),
            "lon": float(customer["longitude"]),
            "status": customer_status(
                customer_id,
                current_minute,
                simulation["service_events"],
            ),
        })

    vehicle_data = []

    for index, schedule in enumerate(simulation["schedules"]):
        route = next(
            (
                item for item in solution["routes"]
                if item["vehicle_id"] == schedule["vehicle_id"]
            ),
            None,
        )

        if route is None:
            continue

        lat, lon = vehicle_position(
            schedule, current_minute, depot
        )

        coords = [
            [leg["from_lat"], leg["from_lon"]]
            for leg in schedule["legs"]
        ]

        if schedule["legs"]:
            last = schedule["legs"][-1]
            coords.append([last["to_lat"], last["to_lon"]])

        vehicle_data.append({
            "id": str(schedule["vehicle_id"]),
            "lat": float(lat),
            "lon": float(lon),
            "route": coords,
            "color": [
                "blue", "purple", "darkgreen", "orange",
                "darkred", "cadetblue", "black", "pink",
            ][index % 8],
        })

    payload = json.dumps({
        "depot": {
            "lat": float(depot["latitude"]),
            "lon": float(depot["longitude"]),
        },
        "customers": customer_data,
        "vehicles": vehicle_data,
    })

    html = r"""
    <div id="map" style="height: HEIGHTpx; width:100%;"></div>
    <link rel="stylesheet"
      href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script>
    const data = PAYLOAD;

    const map = L.map("map").setView(
        [data.depot.lat, data.depot.lon], 12
    );

    L.tileLayer(
        "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
        {
            attribution: '&copy; OpenStreetMap contributors &copy; CARTO',
            maxZoom: 19
        }
    ).addTo(map);

    L.marker([data.depot.lat, data.depot.lon])
        .bindTooltip("Central Depot")
        .addTo(map);

    const customerMarkers = {};

    data.customers.forEach(c => {
        const colors = {
            "Pending": "blue",
            "Being serviced": "orange",
            "Delivered": "green",
            "Unassigned": "gray"
        };

        const marker = L.circleMarker([c.lat, c.lon], {
            radius: 6,
            color: colors[c.status] || "gray",
            fillOpacity: 0.85
        }).bindTooltip(c.id + ": " + c.status);

        marker.on("click", () => {
            marker.bindPopup(
                "<b>" + c.id + "</b><br>Status: " + c.status
            ).openPopup();
        });

        marker.addTo(map);
        customerMarkers[c.id] = marker;
    });

    data.vehicles.forEach(v => {
        if (v.route.length > 1) {
            L.polyline(v.route, {
                color: v.color,
                weight: 4,
                opacity: 0.65
            }).bindTooltip("Route: " + v.id).addTo(map);
        }

        const vehicleIcon = L.divIcon({
            className: "",
            html: '<div style="font-size:20px">🚚</div>',
            iconSize: [24, 24],
            iconAnchor: [12, 12]
        });

        L.marker([v.lat, v.lon], {
            icon: vehicleIcon
        }).bindTooltip("Vehicle " + v.id).addTo(map);
    });

    if (data.customers.length > 0) {
        const points = [
            [data.depot.lat, data.depot.lon],
            ...data.customers.map(c => [c.lat, c.lon])
        ];

        map.fitBounds(points, {
            padding: [25, 25],
            animate: false
        });
    } else {
        map.setView([data.depot.lat, data.depot.lon], 12);
    }
    </script>
    """

    html = (
        html.replace("HEIGHT", str(int(height)))
        .replace("PAYLOAD", payload)
    )

    components.html(html, height=height + 10, scrolling=False)
