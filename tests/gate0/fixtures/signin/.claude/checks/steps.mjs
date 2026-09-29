const CANNOT_RUN = 75;
const email = process.env.TEST_ACCOUNT_EMAIL;
const password = process.env.TEST_ACCOUNT_PASSWORD;

if (!email || !password) {
  console.error("CANNOT RUN  TEST_ACCOUNT_EMAIL and TEST_ACCOUNT_PASSWORD are not set");
  process.exit(CANNOT_RUN);
}

const signIn = (typed) => [
  { fill: { selector: "#email", value: email } },
  { fill: { selector: "#password", value: typed } },
  { click: "#signin" },
];

const arrived = (timeout) => [
  { url: { contains: "/orders" }, timeout },
  { text: { selector: "#who", equals: email }, timeout },
  { count: { selector: ".order", equals: 3 }, timeout },
];

const scenarios = {
  "signed-in": [...signIn(password), ...arrived(5000)],
  "wrong-password": [...signIn(`${password}-wrong`), ...arrived(1500)],
  "signed-out": [
    ...signIn(password),
    ...arrived(5000),
    { click: "#signout" },
    { url: { contains: "/login" } },
    { goto: "/orders" },
    { url: { contains: "/login" } },
    { visible: "#email" },
    { hidden: ".order" },
  ],
  "still-signed-in": [
    ...signIn(password),
    ...arrived(5000),
    { goto: "/orders" },
    { url: { contains: "/login" }, timeout: 1500 },
  ],
};

const steps = scenarios[process.argv[2]];
if (!steps) {
  console.error(`unknown scenario ${process.argv[2]}; known: ${Object.keys(scenarios).join(", ")}`);
  process.exit(2);
}
console.log(JSON.stringify(steps));
