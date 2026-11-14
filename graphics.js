const project_title = "Astrosalud";

function setPageName(){
    var elements = document.querySelectorAll (".project-name");
    elements.forEach(element => {
        element.innerHTML = project_title;
    });
    document.title = project_title;
}
setPageName();

// Referencia al canvas
const $grafica = document.querySelector("#grafica");
// Etiquetas para el eje X
const etiquetas = ["Enero", "Febrero", "Marzo", "Abril"];
// Datos del gráfico
const datosVentas2020 = {
   label: "Ventas por mes",
   data: [5000, 1500, 8000, 5102],
   backgroundColor: 'rgba(54, 162, 235, 0.2)',
   borderColor: 'rgba(54, 162, 235, 1)',
   borderWidth: 1,
};
// Crear el gráfico
new Chart($grafica, {
   type: 'line',
   data: {
       labels: etiquetas,
       datasets: [datosVentas2020],
   },
   options: {
       scales: {
           yAxes: [{
               ticks: {
                   beginAtZero: true,
               },
           }],
       },
   },
});