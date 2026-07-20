import { Tabs } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { GestureHandlerRootView } from "react-native-gesture-handler";
import { Text, View } from "react-native";
import { color } from "@/lib/tokens";

function TabLabel({ label, focused }: { label: string; focused: boolean }) {
  return (
    <View style={{ alignItems: "center", paddingTop: 8 }}>
      <Text
        style={{
          color: focused ? color.silver : "#8B867B",
          fontSize: 12,
          fontWeight: "600",
          letterSpacing: -0.1,
        }}
      >
        {label}
      </Text>
      <View
        style={{
          marginTop: 6,
          height: 2,
          width: 28,
          borderRadius: 1,
          backgroundColor: focused ? color.safelight : "transparent",
        }}
      />
    </View>
  );
}

export default function RootLayout() {
  return (
    <GestureHandlerRootView style={{ flex: 1, backgroundColor: color.graphite }}>
      <StatusBar style="light" />
      <Tabs
        screenOptions={{
          headerShown: false,
          tabBarStyle: {
            backgroundColor: color.selenium,
            borderTopColor: "rgba(218,213,201,0.12)",
            height: 64,
          },
          tabBarShowLabel: false,
        }}
      >
        <Tabs.Screen
          name="index"
          options={{
            tabBarIcon: ({ focused }) => <TabLabel label="Wire" focused={focused} />,
          }}
        />
        <Tabs.Screen
          name="darkroom"
          options={{
            tabBarIcon: ({ focused }) => <TabLabel label="Darkroom" focused={focused} />,
          }}
        />
        <Tabs.Screen
          name="prints"
          options={{
            tabBarIcon: ({ focused }) => <TabLabel label="Prints" focused={focused} />,
          }}
        />
        <Tabs.Screen
          name="studio"
          options={{
            tabBarIcon: ({ focused }) => <TabLabel label="Studio" focused={focused} />,
          }}
        />
        <Tabs.Screen name="signin" options={{ href: null }} />
      </Tabs>
    </GestureHandlerRootView>
  );
}
